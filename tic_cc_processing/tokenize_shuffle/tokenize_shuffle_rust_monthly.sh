#!/bin/bash
# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
# 

# Local directories for input/tmp/output data for each run of tokenize-shuffle
mkdir monthly_local
mkdir tokshuf_tmp
mkdir monthly_tokshuf

# Leave off trailing slashes
input_dir="s3://path/to/your/deduped/data"
output_dir="s3://path/to/your/tokenized/data"

for gs in 01 10
do
    for year in {2023..2024}
    do
        for month in {01..12}
        do
            # Copy input (untokenized) data from S3
            s5cmd sync "${input_dir}/gs_${gs}_of_10/${year}${month}/*" monthly_local/

	        tokshuf-rs/target/release/tokshuf-rust \
            --input monthly_local \
            --local-cell-dir tokshuf_tmp \
            --output monthly_tokshuf \
            --tokenizer "EleutherAI/gpt-neox-20b" \
            --seqlen 2049 \
            --wds-chunk-size 8192 \
            --num-local-cells 512

            # Copy back to S3
            s5cmd sync "monthly_tokshuf/*" ${output_dir}/gs_${gs}_of_10/${year}${month}/

            rm -rf tokshuf_tmp/*
            rm -rf monthly_local/*
            rm -rf monthly_tokshuf/*
        done
    done
done
