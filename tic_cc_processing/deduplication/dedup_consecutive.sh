#!/bin/bash
# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
# 

export AWS_MAX_ATTEMPTS=10
export AWS_RETRY_MODE="standard"

# Leave off trailing slashes

input_dir="inputs_tmp"
#output_dir="s3://path/to/your/deduped/data"


# For only the training and evaluation splits of tic_cc
for gs in 01
do
    prev_month="201305"
    while IFS= read -r cur_month; do
        
	[ -z "$cur_month" ] && continue

        [ "$cur_month" = "$prev_month" ] && continue
	echo "Deduplicating ${cur_month} while using ${prev_month}"

        # Create the Bloom Filter for the previous month
        bff/target/release/bff bff \
           --inputs ${input_dir}/gs_${gs}_of_10/${prev_month}/ \
           --output-directory tmp_outputs_${prev_month}/ \
           --expected-ngram-count 89672202414 \
           --fp-rate 0.01 \
           --remove-type old-both \
           --filtering-threshold 0.8 \
           --min-ngram-size 13 \
           --max-ngram-size 13 \
	   --bloom-filter-file tmp_bloom_filter_${prev_month} \

        # Deduplicate the current month
        bff/target/release/bff bff \
	   --inputs ${input_dir}/gs_${gs}_of_10/${cur_month}/ \
           --output-directory new_outputs_${cur_month}/ \
	   --expected-ngram-count 89672202414 \
           --fp-rate 0.01 \
	   --remove-type old-both \
           --filtering-threshold 0.8 \
           --min-ngram-size 13 \
           --max-ngram-size 13 \
           --bloom-filter-file tmp_bloom_filter_${prev_month} \
	   --no-save-bloom-filter 
	  
        #rm tmp_bloom_filter_${prev_month}

        prev_month=${cur_month}
    done < "$1"
done

# should maybe change the ngram count
