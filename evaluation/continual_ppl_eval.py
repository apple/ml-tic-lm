# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
# 

import argparse
import os
import torch
from smart_open import open
import copy
import subprocess
from datetime import datetime
import time
import pandas as pd
from file_utils import extract_month, aggregate_evals, list_and_sort_model_checkpoints
from utils import update_args_from_openlm_config, set_args_for_val, partition
from open_lm.evaluate import evaluate_loop
from transformers import AutoModelForCausalLM

from open_lm.data import get_data
from open_lm.distributed import init_distributed_device
from open_lm.model import create_params
from open_lm.main import load_model
from open_lm.evaluate import evaluate_loop
from open_lm.file_utils import pt_load
from open_lm.utils.transformers.hf_config import OpenLMConfig
from open_lm.utils.transformers.hf_model import OpenLMforCausalLM

def load_eval_model(args, checkpoint=None, config=None):
    # Assert that only one of hf_model and config is provided
    assert args.hf_model is None, "We don't run TiC-CC evaluatoins for HF models which may have different tokenizers."
    args = copy.deepcopy(args)

    if config is not None:
        args.config = config
        update_args_from_openlm_config(args)

        # Used for evaluating DCLM models since the _swiglutorch configs are only in dclm
        if 'swiglutorch' in args.model:
            args.model = args.model.replace("_swiglutorch", "")
            args.ffn_type = 'swiglu_torch'

        params = create_params(args)
        args.wandb = None
        eval_model = OpenLMforCausalLM(OpenLMConfig(params))
    else:
        raise ValueError("Either a config or hf_model must be provided.")

    if checkpoint is not None:
        args.resume = checkpoint
        if not args.averager_name:
            print(f"Loading checkpoint {checkpoint}")
            args.distributed = False
            load_model(args, eval_model.model, different_seed=True)
            args.distributed = True
        else:
            print(f"Loading checkpoint {checkpoint}")
            checkpoint = pt_load(args.resume, map_location="cpu")
            if "epoch" in checkpoint:
                # resuming a train checkpoint w/ epoch and optimizer state
                start_epoch = checkpoint["epoch"]
                avg_sd = torch.load(checkpoint, map_location="cpu")
                if next(iter(avg_sd.items()))[0].startswith("module"):
                    avg_sd = {k[len("module.") :]: v for k, v in avg_sd.items()}
                eval_model.model.load_state_dict(avg_sd)

        if args.torchcompile:
            print("Using torchcompile")
            eval_model.model = torch.compile(eval_model.model)

        eval_model.model.eval()

    # Set requires grad = False to reduce memory consumption - o/w composer makes a copy of the model.
    for p in eval_model.parameters():
        p.requires_grad = False

    device = init_distributed_device(args)
    eval_model = eval_model.to(device)

    return eval_model, args

def partition_ckpts_and_val_data(args, model_ckpts, val_data):
    if args.num_ckpt_partitions is not None:
        assert args.ckpt_partition is not None
        model_ckpts = partition(model_ckpts, args.num_ckpt_partitions)[args.ckpt_partition]
        print(f"Evaling ckpt partition {args.ckpt_partition} out of {args.ckpt_partition} containing {len(model_ckpts)} ckpts.")
        print(model_ckpts)

    if args.num_val_partitions is not None:
        assert args.val_partition is not None
        val_data = partition(val_data, args.num_val_partitions)[args.val_partition]
        print(f"Evaling val partition {args.val_partition} out of {args.num_val_partitions} containing {len(val_data)} validation sets.")
        print(val_data)

    return model_ckpts, val_data

def get_output_file_name(args):
    dir_path = os.path.join(args.output_dir, args.exp_name)
    os.makedirs(dir_path, exist_ok=True)
    fname_components = [f"eval_{args.exp_name}"]
    if args.num_ckpt_partitions is not None:
        fname_components.append(f"ckpts-{args.ckpt_partition}-of-{args.num_ckpt_partitions}")
    if args.num_val_partitions is not None:
        fname_components.append(f"evals-{args.val_partition}-of-{args.num_val_partitions}")
    fname = "_".join(fname_components) + ".jsonl"
    fname = fname.replace("/", "_")
    return os.path.join(dir_path, fname)

def run_ppl_evals(args):
    # Find the checkpoints to evaluate from a given parent directory. If hf_model is provided, then only one checkpoint is evaluated
    if args.hf_model:
        model_ckpts = zip([None],[None])
    elif args.parent_ckpt_dir is not None:
        model_ckpts = list_and_sort_model_checkpoints(args)
    elif args.ckpts_from_file:
        with open(args.ckpts_from_file, "r") as f:
            ckpts = f.read().splitlines()
        ckpt_configs = [os.sep.join(c.split(os.sep)[:-2] + ["params.txt"]) for c in ckpts]
        model_ckpts = list(zip(ckpts, ckpt_configs))
    else:
        raise NotImplementedError("Need to either specify --hf-model, --parent-ckpt-dir, or --ckpts-from-file")

    print(f"Found {len(model_ckpts)} checkpoints to evaluate in total.")

    # Find the val sets to evaluate on, assuming it's in brace-notation. If s3 path, use pipe: to stream
    with open(args.eval_sets) as f:
        val_data = f.read().splitlines()
    val_data = [f"pipe:aws s3 cp {v} -" if v.startswith("s3://") else v for v in val_data]

    if args.starting_timestep is not None:
        val_data = [v for v in val_data if extract_month(v) >= args.starting_timestep]
    if args.ending_timestep is not None:
        val_data = [v for v in val_data if extract_month(v) <= args.ending_timestep]

    print(f"Found {len(val_data)} eval sets to evaluate in total.")

    # Partition the ckpts and val sets
    model_ckpts, val_data = partition_ckpts_and_val_data(args, model_ckpts, val_data)
    args.val_data = val_data
    output_file = get_output_file_name(args)
    output_dir = os.path.dirname(output_file)
    remote_dir = os.path.join(args.remote_sync, args.exp_name) if args.remote_sync else None

    # Run evals for each checkpoint
    aggregate_results = []
    for checkpoint, config in model_ckpts:
        print(f"Running perplexity evals for checkpoint: {checkpoint}")
        t0 = time.time()
        print("Loading model")
        eval_model, eval_model_args = load_eval_model(args, checkpoint, config)
        print("Model loaded:", time.time() -t0, "seconds.")

        # Allow for overriding the per_gpu_val_batch_size
        if args.per_gpu_val_batch_size is None:
            eval_model_args.per_gpu_val_batch_size = eval_model_args.per_gpu_batch_size // eval_model_args.accum_freq
        else:
            eval_model_args.per_gpu_val_batch_size = args.per_gpu_val_batch_size

        if args.workers is not None:
            eval_model_args.workers = args.workers

        for v in val_data:
            eval_model_args = set_args_for_val(eval_model_args, [v], [args.val_data_key], args.skip_seq_ci, args.skip_tok_ci, args.val_max_pop_ci, args.val_iter_ci)
            data = get_data(eval_model_args, epoch=0, tokenizer=None, skip_train=True)
            results = evaluate_loop(eval_model.model, data["val_list"], 0, eval_model_args, None)
            results[0]['creation_time'] = datetime.now().strftime("%Y_%m_%d-%H_%M_%S")
            aggregate_results.extend(results)
            pd.DataFrame(aggregate_results).to_json(output_file, lines=True, orient='records')

            if args.aggregate_local:
                aggregate_evals(output_dir, output_file="aggregate_evals.jsonl")
            elif args.aggregate_remote and remote_dir is not None:
                temp_dir = os.path.join(output_dir, "temp")
                subprocess.run(["aws", "s3", "sync", remote_dir, temp_dir])
                aggregate_evals(temp_dir, output_file=os.path.join(output_dir, "aggregate_evals.jsonl"))
            if args.remote_sync:
                print("Syncing results to remote")
                subprocess.run(["aws", "s3", "sync", output_dir, remote_dir])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Train models with continual learning.')
    # Arguments that openlm requires when we call load_model or init_distributed_device
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed for reproducibility, when None, will use the seed from the eval config file.",
    )
    parser.add_argument("--fsdp", default=False, action="store_true")
    parser.add_argument("--distributed", default=True, action="store_true")
    parser.add_argument("--resume", default=None, type=str)
    parser.add_argument("--backend-timeout", default=300, type=int)
    parser.add_argument("--force-xformers", action="store_true")
    parser.add_argument("--per-gpu-val-batch-size", type=int, default=None)
    parser.add_argument("--remote-sync", type=str, default=None)
    parser.add_argument("--aggregate_local", action='store_true')
    parser.add_argument("--aggregate_remote", action='store_true')
    parser.add_argument("--torchcompile", action='store_true')

    # Arguments for tic-llm evals
    parser.add_argument('--exp-name', help='Experiment name. If not provided, will attempt to fetch from Bolt.', default=None)
    parser.add_argument('--output-dir', type=str, default="./evals")
    parser.add_argument('--parent-ckpt-dir', help='Parent path of manifest training data in the S3 bucket.', default=None)
    parser.add_argument('--ckpts-from-file', help='Alternative way to specify which checkpoints to evaluate, one url per file.', default=None)
    parser.add_argument('--eval-sets', help='Path to the file containing the list of eval sets.', required=True)
    parser.add_argument('--val-data-key', type=str, default="json.gz")
    parser.add_argument("--tokenizer", type=str, default="EleutherAI/gpt-neox-20b")
    parser.add_argument("--hf_model", type=str, default=None)
    parser.add_argument("--hf-cache-dir", default=None)
    parser.add_argument("--model", default=None, type=str)
    parser.add_argument("--averager-name", help="If specified, load this averager from checkpoint.")
    parser.add_argument("--overwrite", default=False, action="store_true", help="Overwrite existing evals. Otherwise checks if they exist first.")
    parser.add_argument("--workers", type=int, default=None, help="Dataloader works per gpu")
    parser.add_argument(
        "--ckpt-months",
        type=str,
        default=None,
        help="filepath contianing the training checkpoints (i.e. months) to be evaluated or string of months spearated by colon (:)"
    )

    # These arguments only work if using parent-ckpt-dir instead of ckpts-from-file.
    parser.add_argument("--starting-timestep", type=str, default=None, help="Starting month for continual training, used to filter which datasets to train on.")
    parser.add_argument("--ending-timestep", type=str, default=None, help="Starting month for continual training, used to filter which datasets to train on.")
    parser.add_argument("--time-range", type=str, default=None, help="Starting and ending month (inclusive) separted by a colon (e.g., 201305:201512) ")

    parser.add_argument("--num-ckpt-partitions", type=int, default=None)
    parser.add_argument("--ckpt-partition", type=int, default=None)
    parser.add_argument("--num-val-partitions", type=int, default=None)
    parser.add_argument("--val-partition", type=int, default=None)

    # Arguments for bootstrap CI calculations
    parser.add_argument("--skip-seq-ci", default=False, action="store_true")
    parser.add_argument("--skip_tok_ci", default=False, action="store_true")
    parser.add_argument(
        "--val-max-pop-ci",
        default=None,
        action="store",
        type=int,
        help="when running CIs what is the maximum population size for the inner loop",
    )
    parser.add_argument(
        "--val-iter-ci",
        default=10_000,
        action="store",
        type=int,
        help="how many times to sample to construct the CI for the outer loop",
    )

    args = parser.parse_args()

    if args.time_range is not None:
        args.starting_timestep, args.ending_timestep = args.time_range.split(":")

    run_ppl_evals(args)
