# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
# 

import argparse
import os
from smart_open import open
import copy
import subprocess
import yaml
from file_utils import extract_month, download_from_s3, aggregate_evals, min_unique_subdirs, list_and_sort_model_checkpoints, s3_file_exists
from utils import update_nested_dict
import warnings

PPL_EVAL_SCRIPT = "continual_ppl_eval.py"
DOWNSTREAM_EVAL_SCRIPT = "continual_downstream_eval.py"

def get_ppl_eval_commands(args, params_file):
    cmds = []
    for g in range(args.num_gpus):
        cmd = [
            f"CUDA_VISIBLE_DEVICES={g}",
            "python",
            PPL_EVAL_SCRIPT,
            "--distributed",
            "--exp-name", args.exp_name,
            "--parent-ckpt-dir", os.path.dirname(params_file),
            "--eval-sets", args.eval_sets,
            "--per-gpu-val-batch-size", args.per_gpu_val_batch_size,
            "--workers", args.workers,
            "--num-val-partitions", args.num_gpus,
            "--val-partition", g
        ]
        if args.val_max_pop_ci:
            cmd.extend(["--val-max-pop-ci", args.val_max_pop_ci])

        if args.time_range:
            cmd.extend(["--time-range", args.time_range])

        cmd = " ".join([str(c) for c in cmd])
        cmds.append(cmd)
    return cmds


def get_downstream_eval_command(args, params_file, model_checkpoint):
    os.makedirs(os.path.dirname(args.output_file), exist_ok=True)
    if args.hf_model is not None:
        cmd = [
            "torchrun",
            "--nproc_per_node", str(args.num_gpus),
            DOWNSTREAM_EVAL_SCRIPT,
            "--hf-model", args.hf_model,
            "--tokenizer", args.tokenizer,
            "--eval-yaml", args.eval_yaml,
            "--output-file", args.output_file
        ]
    else:
        cmd = [
            "torchrun",
            "--nproc_per_node", str(args.num_gpus),
            DOWNSTREAM_EVAL_SCRIPT,
            "--checkpoint", model_checkpoint,
            "--tokenizer", args.tokenizer,
            "--eval-yaml", args.eval_yaml,
            "--config", params_file,
            "--output-file", args.output_file
        ]

    if args.averager_name:
        cmd.extend(["--averager-name", args.averager_name])
    if args.hf_cache_dir:
        cmd.extend(["--hf-cache-dir", args.hf_cache_dir])
    if args.force_xformers:
        cmd.extend(["--force-xformers"])
    if args.force_eval_download:
        cmd.extend(["--force-eval-download"])
    return cmd


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Evaluate continually trained models with time-dependent evals.')

    # Arguments that open_lm requires when we call load_model or init_distributed_device
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed for reproducibility, when None, will use the seed from the eval config file.",
    )

    parser.add_argument(
        "--num-gpus",
        type=int,
        default=None,
        help="Number of GPUs to use for evaluation. Usually the best is to set this to the number you have on your node.",
    )

    # General arguments for the evaluation script
    parser.add_argument("--eval_config", type=str, help="Path to the eval config file.", required=True)
    parser.add_argument('--exp-name', help='Experiment name which should match an exp-name from your training run', type=str, default=None)
    parser.add_argument("--overwrite-ppl-args", nargs="*", help="Overwrite the perplexity eval arguments.")
    parser.add_argument("--overwrite-downstream-args", nargs="*", help="Overwrite the downstream eval arguments.")
    parser.add_argument('--output-dir', type=str, default="./evals",  help='Local directory for evaluation results')
    parser.add_argument('--logs-dir', type=str, default="./logs", help='Local directory for logs')
    parser.add_argument("--model-cache-dir", default="./models", help="Path to the local directory where model checkpoints are downloaded to.")
    parser.add_argument("--remote-sync", type=str, default="<PATH_TO_S3_EVALUATION_RESULTS>", help="Path to an S3 bucket where evaluation results should be synced to.")
    parser.add_argument("--skip-ppl", action='store_true', help="Skip TiC-CC evaluations.")
    parser.add_argument("--skip-downstream", action='store_true', help="Skip downstream (non-TiC-CC) evaluations.")
    parser.add_argument("--keep-local-ckpts", action='store_true', help="Whether to remove local copies of checkpoints to save disk space.")
    parser.add_argument("--overwrite", default=False, action="store_true", help="Overwrite existing evals. Otherwise skips if they exist already.")
    parser.add_argument(
        "--ckpt-months",
        type=str,
        default=None,
        help="filepath contianing the training checkpoints (i.e. months) to be evaluated or string of months spearated by colon (:)"
    )

    # Arguments for the TiC-CC evaluations
    parser.add_argument('--parent-ckpt-dir', help='Parent path of model sequence in an S3 bucket.', default=None)
    parser.add_argument('--ckpts-from-file', help='Alternative way to specify which checkpoints to evaluate, one url per file.', default=None)
    parser.add_argument('--ppl-eval-sets', help='Path to the file containing the list of eval sets.', type=str, default=None)
    parser.add_argument("--starting-timestep", type=str, default=None, help="Starting month for continual training, used to filter which datasets to train on.")
    parser.add_argument("--ending-timestep", type=str, default=None, help="Starting month for continual training, used to filter which datasets to train on.")
    parser.add_argument("--time-range", type=str, default=None, help="Starting and ending month (inclusive) separted by a colon (e.g., 201305:201512)")
    parser.add_argument("--download-ppl-local", action='store_true', help="Make sure to download locally first.")
    parser.add_argument("--ignore-ppl-failures", action='store_true', help="Ignore failures in perplexity evals.")
    parser.add_argument("--ppl_months", type=str, default=None)

    # Arguments for downstream evals
    parser.add_argument("--hf-model", type=str, default=None, help="Huggingface model name to use for downstream evals.")
    parser.add_argument("--tokenizer", type=str, default="EleutherAI/gpt-neox-20b", help="Huggingface tokenizer to use for downstream evals (defaults to ours).")
    parser.add_argument("--hf-cache-dir", default=None, help="Path to the local directory where huggingface models are cached.")
    parser.add_argument("--force-eval-download", action='store_true', help="Forces re-download of the eval data.")

    args = parser.parse_args()

    assert not (args.skip_ppl and args.skip_downstream), "You cannot skip both perplexity and downstream evals."

    # Infer exp_name from parent_ckpt_dir if not provided
    if args.exp_name is None:
        args.exp_name = os.path.basename(args.parent_ckpt_dir.rstrip("/"))

    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(args.logs_dir, exist_ok=True)
    os.makedirs(args.model_cache_dir, exist_ok=True)

    # Load default configs and overwrite with the provided ones
    with open(args.eval_config, 'r') as f:
        eval_config = yaml.safe_load(f)
    ppl_eval_config = eval_config["perplexity_evals"]
    downstream_eval_config = eval_config["downstream_evals"]

    if args.overwrite_ppl_args:
        for pair in args.overwrite_ppl_args:
            nested_keys, value = pair.split("=")
            keys = nested_keys.split(".")
            update_nested_dict(ppl_eval_config, keys, value)

    if args.overwrite_downstream_args:
        for pair in args.overwrite_downstream_args:
            nested_keys, value = pair.split("=")
            keys = nested_keys.split(".")
            update_nested_dict(downstream_eval_config, keys, value)

    # Get the list of model ckpts and then run both ppl and downstream evals
    if args.time_range is not None:
        args.starting_timestep, args.ending_timestep = args.time_range.split(":")

    output_dir = os.path.join(args.output_dir, args.exp_name)
    remote_dir = os.path.join(args.remote_sync, args.exp_name) if args.remote_sync else None

    if args.hf_model is not None:
        model_ckpts = [(None, None)]
    else:
        model_ckpts = list_and_sort_model_checkpoints(args)

    for i, (ckpt, params_file) in enumerate(model_ckpts):
        # Runn TiC-CC evals unless the model is an external model (with different tokenizer)
        if args.hf_model is None:
            month = extract_month(params_file, default=None)
            print(f"Running evals for month {month}: {ckpt}")

            # Download the model checkpoint and params file locally first.
            ckpt = download_from_s3(ckpt, args.model_cache_dir, num_local_subdirs=4)
            params_file = download_from_s3(params_file, args.model_cache_dir, num_local_subdirs=3)

            # Also downloads the files for the next ckpt in background so that they'll be ready to go when needed
            if i < len(model_ckpts) - 1:
                next_ckpt, next_params = model_ckpts[i+1]
                _ = download_from_s3(next_ckpt, args.model_cache_dir, wait=False, num_local_subdirs=4)
                _ = download_from_s3(next_params, args.model_cache_dir, wait=False, num_local_subdirs=3)

            # Run the TiC-CC evals and then aggregate if using multiple processes. Aggregates before checking success to allow resumptions
            if not args.skip_ppl and (args.ppl_eval_sets or ppl_eval_config.get("eval_sets")):
                ppl_args = copy.deepcopy(args)
                for k, v in ppl_eval_config.items():
                    setattr(ppl_args, k, v)

                ppl_args.remote_sync = "None"   # Don't do the remote sync in each worker process since we'll do it below.
                ppl_args.exp_name = os.path.join(args.exp_name, "ppl_evals", month) if month else os.path.join(args.exp_name, "ppl_evals")
                ppl_args.num_gpus = args.num_gpus if args.num_gpus is not None else ppl_args.num_gpus
                ppl_args.eval_sets = args.ppl_eval_sets if args.ppl_eval_sets is not None else ppl_args.eval_sets

                remote_output_file = os.path.join(args.remote_sync, ppl_args.exp_name, "aggregated_ppl_evals.jsonl")
                if s3_file_exists(remote_output_file) and not args.overwrite:
                    warnings.warn(f"Existing output file already exists at {remote_output_file}, skipping this evaluation as a result.")
                    warnings.warn("Please use the --overwrite flag if you wish to run it anyways.")
                else:
                    # Download the evaluation data locally first for more stable performance
                    if args.download_ppl_local:
                        with open(ppl_args.eval_sets, 'r') as f:
                            shards = f.read().splitlines()
                        local_shards = [
                            download_from_s3(s, "./local_data/ppl_evals/", wait=(s==shards[-1]), num_local_subdirs=min_unique_subdirs(shards))
                            if s.startswith("s3://")
                            else s
                            for s in shards
                        ]
                        if shards != local_shards:
                            # create a new file to feed into eval script with the local paths
                            ppl_args.eval_sets = args.ppl_eval_sets = os.path.splitext(ppl_args.eval_sets)[0] + "_local.txt"
                            with open(ppl_args.eval_sets, 'w') as f:
                                f.write("\n".join(local_shards))
                        else:
                            print("All ppl evals have already been downloaded locally.")

                    ppl_processes = []
                    for cmd in get_ppl_eval_commands(ppl_args, params_file):
                        # As of now we run one command per gpu instead of torchrun. Later, allow for torchrun.
                        print(f"Running cmd for perplexity evals:\n{cmd}")
                        proc = subprocess.Popen(cmd, shell=True)
                        ppl_processes.append(proc)

                    for proc in ppl_processes:
                        proc.wait()

                    print("Aggregating the local perplexity evals into one jsonl and then syncing with remote")
                    aggregate_evals(os.path.join(args.output_dir, ppl_args.exp_name), remove_partials=True)
                    if args.remote_sync:
                        print(f"Syncing results to remote: {remote_dir}")
                        subprocess.run(["aws", "s3", "sync", output_dir, remote_dir], check=True)

                    # TODO: For us, the perplexity evaluation script can occaisionally segfault when running all TiC-CC evaluations
                    # and not all evaluations are completed. The workaround for this that we found was to run the TiC-CC-Wiki evaluations
                    # separately from TiC-CC-News and TiC-CC. This can be done by using eval_configs/ppl_evals/tic_cc_wiki_annual_evals.txt
                    # and eval_configs/ppl_evals/tic_cc_nonwiki_annual_evals.txt as the eval_sets in two separate runs.
                    # This is a temporary fix until we can figure out why the segfaults are happening.
                    if not args.ignore_ppl_failures:
                        assert all(p.returncode == 0 for p in ppl_processes), "perplexity evals failed."
        else:
            month = None

        # Now run the downstream (non TiC-CC) evals
        if not args.skip_downstream:
            print("Running downstream evals")
            downstream_args = copy.deepcopy(args)
            for k, v in downstream_eval_config.items():
                setattr(downstream_args, k, v)

            eval_name = os.path.basename(downstream_args.eval_yaml).split(".")[0]
            basename = f"{month}/{eval_name}.json" if month else f"{eval_name}.json"
            downstream_args.output_file = os.path.join(output_dir, "downstream_evals", basename)

            remote_output_file = os.path.join(args.remote_sync, args.exp_name, "downstream_evals", basename)
            if s3_file_exists(remote_output_file) and not args.overwrite:
                warnings.warn(f"Existing output file already exists at {remote_output_file}, skipping this evaluation as a result.")
                warnings.warn("Please use the --overwrite flag if you wish to run it anyways.")
            else:
                downstream_args.num_gpus = args.num_gpus if args.num_gpus is not None else downstream_args.num_gpus
                cmd = get_downstream_eval_command(downstream_args, params_file, ckpt)

                print(f"Running cmd for downstream eval:\n{cmd}")
                subprocess.run(cmd, check=True)

                if args.remote_sync:
                    print(f"Syncing results to remote: {remote_dir}")
                    subprocess.run(["aws", "s3", "sync", output_dir, remote_dir], check=True)

        # By default remove local checkpoints to save disk space (but user can choose to keep them if they want)
        if not args.keep_local_ckpts:
            print("Removing locally downloaded checkpoint and params file to prevent storage accumulation.")
            if ckpt is not None:
                subprocess.run(f"rm -rf {ckpt}", shell=True)
            if params_file is not None:
                subprocess.run(f"rm -rf {params_file}", shell=True)
