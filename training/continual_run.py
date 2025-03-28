# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
# 

import argparse
import os
import re
import fsspec
import copy
import subprocess
import json
from smart_open import open
from file_utils import extract_unique_parts, glob_files, s3_file_exists, read_params_from_yaml
from utils import cosine_plus_ar_max_lr, STEPS_PER_MONTH

def natural_key(string_):
    """See http://www.codinghorror.com/blog/archives/001018.html"""
    return [int(s) if s.isdigit() else s for s in re.split(r"(\d+)", string_.lower())]


def get_latest_checkpoint(path: str):
    is_s3 = path.startswith("s3")
    fs, root_path = fsspec.core.url_to_fs(path)
    checkpoints = fs.glob(os.path.join(root_path, "epoch_*.pt"))
    if checkpoints:
        checkpoints = sorted(checkpoints, key=natural_key)
        return f"s3://{checkpoints[-1]}" if is_s3 else checkpoints[-1]
    return None


def list_and_sort_manifest_files(args):
    manifest_paths = glob_files(args.parent_dataset_manifest, suffixes=args.manifest_suffixes)
    datasets = extract_unique_parts(manifest_paths) # assumes that manifest paths only differ in the dates, returns List[(date, manifest_path)]
    datasets.sort(key=lambda x: x[0])               # sort by the dates

    if args.starting_timestep is not None:
        datasets = [d for d in datasets if d[0] >= args.starting_timestep]

    if args.ending_timestep is not None:
        datasets = [d for d in datasets if d[0] <= args.ending_timestep]

    return datasets


def construct_command(args, config_):
    config = copy.deepcopy(config_)

    # Start constructing the command with base command and environment-dependent parts
    num_nodes = os.environ.get('NUM_NODES', '1')  # Default to 1 if not set
    node_rank = os.environ.get('NODE_RANK', '0')  # Default to 0 if not set
    master_addr = os.environ.get('MASTER_ADDR', 'localhost')  # Default if not set
    master_port = os.environ.get('MASTER_PORT', '29500')  # Default port if not set

    if args.multi_node:
        command = f"""torchrun --nproc-per-node 8 \\
            --nnodes {num_nodes} \\
            --node_rank {node_rank} \\
            --max_restarts=0 \\
            --rdzv_backend c10d \\
            --rdzv_endpoint "{master_addr}:{master_port}" \\
            --rdzv_conf "timeout=3000,read_timeout=10000" \\
            -m open_lm.main"""
    else:
        command = """torchrun --nproc-per-node 8 \\
            -m open_lm.main"""

    # Iterate over the config to append each parameter
    for key, value in config.items():
        if isinstance(value, bool):
            # For boolean parameters, include them only if True
            if value:
                command += f" --{key.replace('_', '-')}  \\\n"
        else:
            # For other types of parameters, include them with their values
            command += f" --{key.replace('_', '-')} {value} \\\n"
    return command

def modify_training_config(config, args):
    config['log_local'] = args.try_local_ckpt

    if args.logs:
        config['logs'] = args.logs

    if args.remote_sync:
        config['remote_sync'] = args.remote_sync

    if args.logs:
        config['logs'] = args.logs

    if args.remote_sync:
        config['remote_sync'] = args.remote_sync

    if args.wd is not None:
        config['wd'] = args.wd

    if args.lwf_weight is not None:
        config['lwf_weight'] = args.lwf_weight
        config['lwf_kl'] = args.lwf_kl

    if args.ewc_weight is not None:
        config['ewc_weight'] = args.ewc_weight
        config['ewc_num_iterations'] = args.ewc_num_iterations
        config['ewc_log_loss'] = args.ewc_log_loss

    if args.accum_freq is not None:
        config['accum_freq'] = args.accum_freq

    if args.lr is not None:
        config['lr'] = args.lr

    if args.lr_scheduler is not None:
        config['lr_scheduler'] = args.lr_scheduler
        if config['lr_scheduler'] == 'rsqrt':
            config['lr_rsqrt_cooldown'] = args.lr_rsqrt_cooldown

    if args.lr_cooldown_end is not None:
        config['lr_cooldown_end'] = args.lr_cooldown_end

    if args.warmup is not None:
        config['warmup'] = args.warmup

    if args.optimizer is not None:
        config['optimizer'] = args.optimizer

    if args.seed is not None:
        config['seed'] = args.seed

    if args.grad_clip_norm is not None:
        config['grad_clip_norm'] = args.grad_clip_norm

    if args.samples_per_timestep:
        config['train_num_samples'] = args.samples_per_timestep
    else:
        config['train_num_samples'] = config['train_num_samples'] // args.num_timesteps

    return config


def run_continual_training(args):
    # List the sequence of datasets to train on
    datasets = list_and_sort_manifest_files(args)
    exp_name = args.exp_name
    print(f"Found {len(datasets)} datasets to train on\n{datasets}")

    # Can use args.num_timesteps to limit the number of timesteps to train on (such as for hyperparameter search)
    if args.num_timesteps is None:
        args.num_timesteps = len(datasets)
    datasets = datasets[:args.num_timesteps]

    # Prepare the config/arguments for openLM training
    config = read_params_from_yaml(args.config)
    config = modify_training_config(config, args)   # These modifications are common across all timesteps
    local_logs = config['logs']
    remote_sync = config['remote_sync']

    # Loop over the continaul training datasets sequentially
    last_checkpoint = args.init_ckpt
    initial_max_lr = config['lr']
    prev_local_logs_path = None
    warmup_init = 0

    for i, (yearmonth, dataset_path) in enumerate(datasets):
        local_logs_path = os.path.join("open_lm", local_logs, exp_name, yearmonth) if not args.is_non_continual else os.path.join("open_lm", local_logs, exp_name)
        remote_sync_path = os.path.join(remote_sync, exp_name, yearmonth) if not args.is_non_continual else os.path.join(remote_sync, exp_name)

        # File that indicates the training has finished for this month
        training_finished_path = f"{remote_sync_path}/training_finished.txt"

        print(f"Training on {yearmonth} with dataset: {dataset_path}")
        print("Local logs will save to:", local_logs_path)
        print("Remote logs will save to:", remote_sync_path)
        print(f"Beginning timestep that will end up at: {training_finished_path}")

        # For using an AR schedule for the learning rate across rounds
        if args.use_ar_schedule:
            warmup_init = int(config['warmup']) if i == 0 else warmup_init + int(config['warmup'])
            config['lr'] = cosine_plus_ar_max_lr(
                steps_prev=STEPS_PER_MONTH[args.scale] * i, # TODO: Combine scale with config name?
                steps_new=STEPS_PER_MONTH[args.scale],
                warmup_init=warmup_init,
                warmup_new=int(config['warmup']),
                max_lr_init=float(initial_max_lr),
                end_lr=float(config['lr_cooldown_end'])
            )

        # Skip months that have already been trained on
        if s3_file_exists(training_finished_path):
            print(f"Training already completed for {yearmonth}. Skipping...")
            last_checkpoint = get_latest_checkpoint(f'{remote_sync_path}/checkpoints/')
            print("Last checkpoint: ", last_checkpoint)

            if last_checkpoint is not None and last_checkpoint.startswith("open_lm/"):
                last_checkpoint = last_checkpoint.replace("open_lm/", "", 1)

            print("Last checkpoint from open_lm: ", last_checkpoint)
            continue

        # Assumption: the balanced manifest exists in same directory as the imbalanced one and has the _balanced suffix
        if args.try_balanced_manifest or args.force_balanced:
            dataset_path = dataset_path.replace("manifest.jsonl", "manifest_balanced.jsonl")
            # If force_balanced is set, generate a balanced manifest from imbalanced one
            if args.force_balanced:
                print(f"Creating a balanced manifest for month {yearmonth} training looking for shards of size {args.force_balanced}.")
                with open(dataset_path, 'r') as f:
                    lines = f.read().splitlines()
                    lines = [json.loads(l) for l in lines]
                bal_lines = [json.dumps(l) for l in lines if l['num_sequences'] == args.force_balanced]

                with open(dataset_path, 'w') as f:
                    f.write('\n'.join(bal_lines))

            # Check if balanced manifest exists
            assert s3_file_exists(dataset_path), f"Balanced manifest not found for month {yearmonth} training: {dataset_path}"
            print(f"Using balanced manifest for month {yearmonth} training: {dataset_path}")

        # Per-month configuration updates
        config['dataset_manifest'] = dataset_path
        config['name'] = os.path.join(exp_name, yearmonth) if not args.is_non_continual else exp_name
        if last_checkpoint:
            config['pretrained'] = last_checkpoint

        if args.warmup_usage == 'none' or (args.warmup_usage == 'first' and i > 0):
            config['warmup'] = 0

        # Construct the command to run openLM training. These elements are different for each month
        command = construct_command(args, config)
        command_with_directory_change = f"cd open_lm && {command}"
        with open(f'{yearmonth}_local.txt', 'w') as f:
            f.write(command)

        # Execute the training command
        print("Running command:\n", command)
        subprocess.run(command_with_directory_change, shell=True, check=True)

        with open(training_finished_path, 'w') as f:
            f.write(command)

        # Update last_checkpoint for the next iteration. Searches local logs path first, then remote sync path to save unnecessary download
        print(f"Searching local logs path for latest checkpoint: {local_logs_path}/checkpoints/")
        last_checkpoint = get_latest_checkpoint(f'{local_logs_path}/checkpoints/')
        if last_checkpoint is None or not args.try_local_ckpt:
            print(f"Local checkpoint not found. Searching remote sync path: {remote_sync_path}/checkpoints/")
            last_checkpoint = get_latest_checkpoint(f'{remote_sync_path}/checkpoints/')
        elif last_checkpoint.startswith("open_lm/"):
            last_checkpoint = last_checkpoint.replace("open_lm/", "", 1)
        print("Last checkpoint: ", last_checkpoint)

        # Delete local copies of previous checkpoints that are no longer neede
        if prev_local_logs_path is not None and args.delete_previous_logs and os.path.exists(prev_local_logs_path):
            print(f"Deleting logs from previous timestep: {prev_local_logs_path}")
            subprocess.run(f"rm -rf {prev_local_logs_path}", shell=True, check=True)

        prev_local_logs_path = local_logs_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Train models with continual learning.')
    parser.add_argument('--exp-name', help='Experiment name', required=True)
    parser.add_argument('--config', help='Path to the configuration YAML file.', default='configs/3b-2x.yaml')
    parser.add_argument('--scale', help='Scale of the full run.', default=None)
    parser.add_argument('--logs', help='Local path to save logs within the open_lm directory.', default="./logs/")
    parser.add_argument('--remote-sync', help='Remote sync location.', default="<YOUR_S3_PATH_FOR_CHECKPOINTS>")
    parser.add_argument('--parent-dataset-manifest', help='Parent path of manifest training data in the S3 bucket.', required=True)
    parser.add_argument('--init-ckpt', help='Very inital chekpoint for start of continual training. If not provided, will start from random initalization.', default=None)
    parser.add_argument('--multi-node', action="store_true", help="multi-node training")
    parser.add_argument('--num-timesteps', help='Number of continual training iterations (i..e, months).', default=None, type=int)
    parser.add_argument("--samples-per-timestep", type=int, default=None)
    parser.add_argument('--accum-freq', help='Number of steps to accumulate gradients over', default=None, type=int)
    parser.add_argument("--try-local-ckpt", action="store_true", help="Try to use local checkpoint first before downloading from S3 in between timesteps.")
    parser.add_argument("--try-balanced-manifest", help="Try to use balanced manifest for training.", action="store_true")
    parser.add_argument("--force-balanced", help="Force using balanced manifest for training. Generates a balanced manifest from an imbalanced one", type=int, default=None)
    parser.add_argument("--is-non-continual", help="If the dataset is uniform, do not include yearmonth in remote sync", action="store_true")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--manifest-suffixes", nargs="+", default=["/manifest.jsonl"])
    parser.add_argument("--time-range", type=str, default=None, help="Starting and ending month (inclusive) separted by a colon (e.g., 201305:201512) ")
    parser.add_argument("--starting-timestep", type=str, default=None, help="Starting month for continual training, used to filter which datasets to train on.")
    parser.add_argument("--ending-timestep", type=str, default=None, help="Ending month for continual training, used to filter which datasets to train on.")
    parser.add_argument('--delete-previous-logs', action="store_true", help="Delete logs from previous timestep before starting the training of next one.")

    # Arguments to define the hyperparameters such as learning rate schedule
    parser.add_argument('--warmup', help='Number of warmup steps', default=None, type=int)
    parser.add_argument('--warmup-usage', help='Which continual rounds to apply warmup in.', default='all', choices=['all', 'none', 'first'])
    parser.add_argument('--lr', help='Maximum learning rate in each cycle', default=None, type=float)
    parser.add_argument('--wd', help='Weight decay in each cycle', default=None, type=float)
    parser.add_argument("--use-ar-schedule", action="store_true", help="Use AR schedule for learning rate.")
    parser.add_argument("--lr-scheduler", type=str, default=None, help="Learning rate scheduler to use.")
    parser.add_argument("--lr-rsqrt-cooldown", type=int, default=None, help="Number of steps to cooldown for when using rsqrt scheduler.")
    parser.add_argument("--lr-cooldown-end", type=float, default=None, help="End learning rate.")
    parser.add_argument("--optimizer", type=str, default=None, help="Optimizer to use. If None, will use AdamW, the default in open_lm.")
    parser.add_argument("--grad-clip-norm", type=float, default=None, help="Gradient clipping norm.")

    # Additional arguments for lwf
    parser.add_argument("--lwf-weight", type=float, default=None, help="Weight for LWF loss")
    parser.add_argument("--lwf-kl", action="store_true", help="Use KL divergence for LWF loss")

    # Additional arguments fpr ewc
    parser.add_argument("--ewc-weight", type=float, default=None, help="Weight for EWC loss")
    parser.add_argument("--ewc-num-iterations", type=int, default=1000, help="EwC number of approximation steps")
    parser.add_argument("--ewc-log-loss", action="store_true", help="Log the loss for EWC (not strictly necessary for training)")

    args = parser.parse_args()

    # Infer config file and scale from each other, giving priority to scale
    if args.scale is None:
        args.scale = os.path.basename(args.config).split(".")[0]
    elif not os.path.exists(f"configs/{args.scale}.yaml"):
        args.config = f"configs/{args.scale}.yaml"

    if args.time_range is not None:
        args.starting_timestep, args.ending_timestep = args.time_range.split(":")

    run_continual_training(args)
