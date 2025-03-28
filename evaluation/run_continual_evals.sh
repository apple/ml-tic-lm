#!/bin/bash

# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

export AWS_MAX_ATTEMPTS=10
export AWS_RETRY_MODE="standard"
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

ngpus=8
exp_name="YOUR_CHOSEN_EXP_NAME"
ckpt_dir="s3://path/to/your/checkpoints/dir/"
remote_eval_dir="s3://path/to/your/evaluation/dir/"


# Run continual evaluations
# Note 1: By default, TiC-CC evals are run within unified_tic_wiki.yaml but not the other two
# Note 2: If you have sufficient disk space (i.e., >120GB for 3B models), you can add --keep-local-ckpts to avoid re-downloading models across evaluations
for eval_config in "unified_tic_wiki.yaml" "unified_tic_stackexchange.yaml" "unified_tic_codedocs.yaml"
do
python continual_eval.py \
 --eval_config eval_configs/${eval_config} \
 --exp-name ${exp_name} \
 --parent-ckpt-dir ${ckpt_dir}${exp_name} \
 --time-range "201305:202407" \
 --num-gpus ${ngpus} \
 --download-ppl-local \
 --ckpt-months first_per_year.txt \
 --remote-sync ${remote_eval_dir}
done

# Run static evaluations
for eval_config in "static_evals.yaml"
do
python continual_eval.py \
 --eval_config eval_configs/${eval_config} \
 --exp-name ${exp_name} \
 --parent-ckpt-dir ${ckpt_dir}${exp_name} \
 --time-range "202407:202407" \
 --num-gpus ${ngpus} \
 --download-ppl-local \
 --remote-sync ${remote_eval_dir} \
 --skip-ppl
done
