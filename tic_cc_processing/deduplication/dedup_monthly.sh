#!/bin/bash
# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
# 

export AWS_MAX_ATTEMPTS=10
export AWS_RETRY_MODE="standard"

# Leave off trailing slashes
input_dir="s3://path/to/your/data"
output_dir="s3://path/to/your/deduped/data"

# For only the training and evaluation splits of tic_cc
for gs in 01 10
do
    for year in {2013..2024}
    do
        for month in {01..12}
        do
            bff/target/release/bff bff \
                --inputs ${input_dir}/gs_${gs}_of_10/${year}${month}/ \
                --output-directory ${output_dir}/gs_${gs}_of_10/${year}${month}/ \
                --expected-ngram-count 89672202414 \
                --fp-rate 0.01 \
                --no-save-bloom-filter \
                --remove-type old-both \
                --filtering-threshold 0.8 \
                --min-ngram-size 13 \
                --max-ngram-size 13
        done
    done
done
