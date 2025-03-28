#!/bin/bash
# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
# 

export AWS_MAX_ATTEMPTS=10
export AWS_RETRY_MODE="standard"
input_dir=s3://path/to/your/deduped/data/
dest_dir=s3://path/to/your/tokenized/data/

for gs in 01
do
    for year in {2013..2024}
    do
        for month in {01..12}
        do
            python tokenize_shuffle_ray.py \
                --input ${input_dir}/gs_${gs}_of_10/${year}${month} \
                --output ${dest_dir}/gs_${gs}_of_10/${year}${month} \
                --tokenization_num_cpus 2 \
                --ray_spill_location "/mnt/ray_tmp"
        done
    done
done
