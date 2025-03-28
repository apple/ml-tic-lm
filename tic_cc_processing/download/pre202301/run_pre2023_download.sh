#!/bin/bash
# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

# Leave out trailing slash in parent_dest_dir
parent_dest_dir="s3://path/to/your/raw/data"

for gs in 01 10
do
    wget https://ml-site.cdn-apple.com/datasets/tic-lm/pre2023_cc_paths/dclm_pool_paths_gs_${gs}_of_10.txt
    dest_dir=${parent_dest_dir}/gs_${gs}_of_10
    python generate_copy_cmds.py --input dclm_pool_paths_gs_${gs}_of_10.txt --dest-dir ${dest_dir} --output copy_cmds_gs_${gs}.txt
    s5cmd --retry-count 20 --log error --stat run copy_cmds_gs_${gs}.txt | tee s5cmd_log_gs_${gs}_of_10.txt | tail -n 4
done
