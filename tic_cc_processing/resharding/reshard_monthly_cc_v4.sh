#!/bin/bash
# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

export AWS_MAX_ATTEMPTS=10
export AWS_RETRY_MODE="standard"

for gs in {01..10}
do
    for year in {2013..2022}
    do
        for month in {01..12}
        do
            /root/miniconda/bin/python reshard_worker_large_string.py --base-dir s3://path/to/your/data/for_resharding --skip-stats-merge --batch-size 15 --num-cpus 2
        done
    done
done
