# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
# 

import yaml
from smart_open import open

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
