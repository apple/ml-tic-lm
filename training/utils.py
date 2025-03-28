# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
# 

import yaml
from smart_open import open
import math

STEPS_PER_MONTH = {
    "3b_2x": 1887,
    '3b_4x': 3774,
    "3b_6x": 5661,
}

def config_to_command(config):
    cmd = []
    for k, v in config.items():
        if v is None:
            continue
        elif isinstance(v, bool) and v:
            cmd.append(f"--{k.replace('_', '-')}")
        else:
            cmd.append(f"--{k.replace('_', '-')}")
            cmd.append(str(v))
    return cmd

def update_nested_dict(d, keys, value):
    """Recursively updates nested dictionary keys."""
    key = keys.pop(0)
    if len(keys) == 0:
        d[key] = value
    else:
        if key not in d:
            d[key] = {}
        update_nested_dict(d[key], keys, value)

def update_args_from_openlm_config(args):
    with open(args.config, "r") as f:
        config = yaml.safe_load(f)

    setattr(args, "backend_timeout", None)
    for k, v in config.items():
        if k == "model" and args.model != None:
            continue
        if v == "None":
            v = None

        # we changed args
        if k == "batch_size":
            k = "per_gpu_batch_size"
        if k == "val_batch_size":
            k = "per_gpu_val_batch_size"
        if k == "val_data" and hasattr(args, 'val_data') and args.val_data != None:
            continue

        # For forcing xformers
        if args.force_xformers:
            if k == "attn_name":
                v = "xformers_attn"
            if k == "torchcompile":
                v = False

        setattr(args, k, v)

def set_args_for_val(args, data, key, skip_seq_ci, skip_tok_ci, val_max_pop_ci=None, val_iter_ci=10000):
    setattr(args, "val_data", data)
    setattr(args, "val_data_key", key)
    setattr(args, "squash_mask_left", True)
    setattr(args, "target_mask_individual", 50400)
    setattr(args, "target_mask_left", 50300)
    setattr(args, "val_seq_ci", False if skip_seq_ci else True)
    setattr(args, "val_tok_ci", False if skip_tok_ci else True)
    setattr(args, "val_max_pop_ci", val_max_pop_ci)
    setattr(args, "val_iter_ci", val_iter_ci)
    return args

def partition(lst, num_lists):
    # Calculate the size of each sublist and how many extra elements are there
    sublist_size = len(lst) // num_lists
    remainder = len(lst) % num_lists

    # Initialize variables
    partitions = []
    start = 0

    # Create sublists
    for _ in range(num_lists):
        if remainder > 0:
            end = start + sublist_size + 1
            remainder -= 1
        else:
            end = start + sublist_size

        partitions.append(lst[start:end])
        start = end

    return partitions

def cosine_decay(current_step, max_lr=3e-3, total_steps=1887, end_lr=3e-05, warmup=5000):
    """
    Calculate learning rate using cosine decay with a target final learning rate.

    Parameters:
        max_lr (float): Initial learning rate.
        current_step (int): Current step in the training process.
        total_steps (int): Total number of steps in the training process.
        end_lr (float): Target final learning rate.

    Returns:
        float: Learning rate at the current step.
    """
    if current_step < warmup:
        return max_lr * (current_step + 1) / warmup

    cosine_decay = 0.5 * (1 + math.cos(math.pi * (current_step - warmup) / (total_steps - warmup)))
    decayed_lr = (max_lr - end_lr) * cosine_decay + end_lr
    return decayed_lr

def cosine_plus_ar_max_lr(steps_prev=0, steps_new=1887, warmup_init=50, warmup_new=50, max_lr_init=1e-3, end_lr=3e-05):
    maxlr_step = steps_prev + warmup_new
    total_steps = steps_prev + steps_new

    print(f"Previous steps: {steps_prev}, Total steps: {total_steps}, Max_lr step: {maxlr_step}")

    return cosine_decay(
        maxlr_step,
        max_lr=max_lr_init,
        total_steps= total_steps,
        end_lr=end_lr,
        warmup=warmup_init
    )
