# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
# 

import os
import re
from smart_open import open
import boto3
import glob
import fsspec
import subprocess
import re
from smart_open import open
import subprocess
from pathlib import Path
from botocore.exceptions import NoCredentialsError
from constants import FIRST_MONTH, LAST_MONTH

def download_from_s3(s3_url, output_dir, num_local_subdirs=3, profile=None, overwrite=False, wait=True):
    if profile is not None:
        profile = f"--profile {profile}"
    else:
        profile = ""

    try:
        local_subdirs = os.sep.join(Path(s3_url).parts[-num_local_subdirs:])
        local_filename = os.path.join(output_dir, local_subdirs)

        if not overwrite and os.path.exists(local_filename):
            print(f"File {local_filename} already exists. Skipping download.")
            return local_filename

        print(f"Downloading {s3_url} to {local_filename}")
        if wait:
            subprocess.run(f"aws s3 cp {s3_url} {local_filename} {profile}", shell=True, check=True)
        else:
            subprocess.Popen(f"aws s3 cp {s3_url} {local_filename} {profile}", shell=True)
        return local_filename
    except NoCredentialsError:
        print("Credentials not available for AWS S3.")
        return None

def aggregate_evals(output_dir, output_file=None, remove_partials=False):
    if output_file is None:
        output_file = os.path.join(output_dir, "aggregated_ppl_evals.jsonl")

    # Concate all evals into one file
    eval_files = glob.glob(f"{output_dir}/*.jsonl", recursive=True)
    # Skip the output file if it already exists
    eval_files = [e for e in eval_files if output_file not in e]
    with open(output_file, "w") as o:
        for eval_file in eval_files:
            with open(eval_file, "r") as i:
                o.write(i.read())
            if remove_partials and os.path.exists(eval_file):
                os.remove(eval_file)

    return output_file

def extract_month(path, boundary="/", default=None):
    # Assumes that months always appear in the path as a subfolder
    if boundary=="/":
        pattern = re.compile(r"/(20\d{4,4})/")
    # Assumes that months always appear as a chunk of exactly 6 digits
    elif boundary=="word":
        pattern = re.compile(r"\b(20\d{4,4})\b")

    month = default
    if pattern.search(path):
        month = pattern.search(path).group(1)

    return month

def natural_key(string_):
    """See http://www.codinghorror.com/blog/archives/001018.html"""
    return [int(s) if s.isdigit() else s for s in re.split(r"(\d+)", string_.lower())]

def find_common_prefix_ending_with_slash(paths):
    """Finds largest common prefix ending with '/'."""
    if not paths: return ""
    shortest = min(paths, key=len)
    for i, char in enumerate(shortest):
        if any(path[i] != char for path in paths):
            return shortest[:i].rpartition('/')[0] + '/'
    return shortest.rpartition('/')[0] + '/'

def find_common_suffix(paths):
    """Finds largest common suffix."""
    if not paths: return ""
    shortest = min(paths, key=len)
    for i, char in enumerate(reversed(shortest)):
        if any(path[-i-1] != char for path in paths):
            return shortest[-i:]
    return shortest[-i:]

def extract_unique_parts(paths, prefix=None, suffix=None):
    """Pairs unique parts of paths with full paths, removing common_prefix and suffix correctly."""
    result = []
    prefix = find_common_prefix_ending_with_slash(paths) if prefix is None else prefix
    suffix = find_common_suffix(paths) if suffix is None else suffix
    prefix_len = len(prefix)
    suffix_len = len(suffix)
    for path in paths:
        if path.startswith(prefix) and path.endswith(suffix):
            # Remove common prefix from start and suffix from end
            unique_part = path[prefix_len:-suffix_len]
            result.append((unique_part.replace('/', '_'), path))
    return result

def glob_files(path, suffixes=None):
    """
    Glob files based on a given path and suffix.
    Supports both local and S3 paths.

    :param path: path to glob. Can be local or S3 (e.g., s3://bucket-name/path/)
    :param suffix: suffix of files to match. Defaults to ".jsonl"
    :return: list of file paths matching the pattern
    """
    if suffixes is None:
        suffixes = ["manifest.jsonl"]

    if path.startswith("s3://"):
        # Use boto3 for S3 paths
        s3 = boto3.client("s3")
        bucket_name, prefix = path[5:].split("/", 1)

        # Ensure the prefix ends with a '/'
        if not prefix.endswith("/"):
            prefix += "/"

        # List the objects in the bucket with the given prefix
        paginator = s3.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)
        all_files = [f"s3://{bucket_name}/{obj['Key']}" for objects in pages for obj in objects.get("Contents", [])]

        # Filter out the files based on the suffix
        matching_files = [f for f in all_files if any(f.endswith(suffix) for suffix in suffixes)]

    else:
        # Use glob for local paths
        matching_files = []
        for suffix in suffixes:
            search_pattern = f"{path.rstrip('/')}/**/*{suffix}"
            matching_files.extend(glob.glob(search_pattern, recursive=True))
            print("matching files with suffix: ", suffix)
            print(matching_files)

    return matching_files

def get_latest_checkpoint(path: str):
    is_s3 = path.startswith("s3")
    fs, root_path = fsspec.core.url_to_fs(path)
    checkpoints = fs.glob(os.path.join(root_path, "epoch_*.pt"))
    if checkpoints:
        checkpoints = sorted(checkpoints, key=natural_key)
        return f"s3://{checkpoints[-1]}" if is_s3 else checkpoints[-1]

    return None

def s3_file_exists(s3_path):
    s3 = boto3.resource('s3')
    bucket_name = s3_path.split('/')[2]
    key = '/'.join(s3_path.split('/')[3:])

    bucket = s3.Bucket(bucket_name)
    objects = list(bucket.objects.filter(Prefix=key))
    return len(objects) > 0 and objects[0].key == key


def min_unique_subdirs(file_paths):
    # Split paths into components
    paths_split = [Path(path).parts for path in file_paths]

    # Function to check uniqueness of paths truncated to a given depth
    def unique_up_to_depth(depth):
        seen = set()
        for path in paths_split:
            truncated_path = tuple(path[-depth:])
            if truncated_path in seen:
                return False
            seen.add(truncated_path)
        return True

    # Find the maximum depth to check (i.e., the length of the longest path)
    max_depth = max(len(path) for path in paths_split)

    # Check each depth from 1 to max_depth
    for depth in range(1, max_depth + 1):
        if unique_up_to_depth(depth):
            return depth

    # If no unique depth is found, return the max_depth (fallback)
    return max_depth

def list_and_sort_model_checkpoints(args, sort_ckpts=True):
    """
    Assumes that the model checkpoints are stored in the following format:

    args.parent_ckpt_dir/{YYYYMM}/
        checkpoints/
            epoch_1.pt
            epoch_2.pt
            ...
        params.txt

    where args.parent_ckpt_dir is the parent directory of all monthly checkpoints.
    """
    ckpt_configs = glob_files(args.parent_ckpt_dir, suffixes=["params.txt"])
    ckpt_configs = sorted(ckpt_configs) if sort_ckpts else ckpt_configs

    if args.starting_timestep is not None:
        ckpt_configs = [c for c in ckpt_configs if extract_month(c, default=LAST_MONTH) >= args.starting_timestep]

    if args.ending_timestep is not None:
        ckpt_configs = [c for c in ckpt_configs if extract_month(c, default=FIRST_MONTH) <= args.ending_timestep]

    if args.ckpt_months is not None:
        if os.path.exists(args.ckpt_months):
            with open(args.ckpt_months, 'r') as f:
                allowed_months = f.read().splitlines()
        else:
            allowed_months = args.ckpt_months.split(":")

        ckpt_configs = [c for c in ckpt_configs if extract_month(c, default=None) in allowed_months]

    ckpt_dirs = [os.path.dirname(c) for c in ckpt_configs]
    ckpts = [get_latest_checkpoint(os.path.join(c, "checkpoints")) for c in ckpt_dirs]

    return list(zip(ckpts, ckpt_configs))