# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#
"""
StackExchange Dump Processor Generator

Generates a bash script for parallel processing of StackExchange data dumps.

Usage:
1. Set variables: src_data_folder, dst_data_folder, s3_path, max_disk_usage_gb
2. Run: python generate_stackexchange_processor.py
3. Execute generated script: bash process_stackexchange_dumps.sh
"""

import os
import argparse

import psutil


def get_file_size_gb(file_path):
    return os.path.getsize(file_path) / (1024 * 1024 * 1024)


def generate_bash_script(
    src_data_folder,
    dst_data_folder,
    s3_path,
    output_file,
    max_ram_usage_gb,
    max_disk_usage_gb,
):
    categories = [
        d
        for d in os.listdir(src_data_folder)
        if os.path.isdir(os.path.join(src_data_folder, d)) and d != "stackoverflow"
    ]

    command_file = []

    # Add shebang and set variables
    command_file.append("#!/bin/bash\n\n")
    command_file.append(f"SRC_DATA_FOLDER='{src_data_folder}'\n")
    command_file.append(f"DST_DATA_FOLDER='{dst_data_folder}'\n")
    command_file.append(f"S3_PATH='{s3_path}'\n")
    command_file.append(f"MAX_RAM_USAGE_KB={int(max_ram_usage_gb * 1024 * 1024)}\n\n")

    # Add ulimit command
    command_file.append("# Set maximum virtual memory\n")
    command_file.append(f"ulimit -v {int(max_ram_usage_gb * 1024 * 1024)}\n\n")

    # Create destination folder
    command_file.append(f"mkdir -p '{dst_data_folder}'\n\n")

    # Group categories by estimated disk usage
    category_sizes = []
    for category in categories:
        category_7z = os.path.join(
            src_data_folder, category, f"{category}.stackexchange.com.7z"
        )
        if os.path.exists(category_7z):
            size = (
                get_file_size_gb(category_7z) * 10
            )  # Estimate total disk usage as 7 times 7z file size
            category_sizes.append((category, size))

    # Add StackOverflow if it exists
    stackoverflow_dir = os.path.join(src_data_folder, "stackoverflow")
    if os.path.exists(stackoverflow_dir):
        stackoverflow_size = sum(
            get_file_size_gb(os.path.join(stackoverflow_dir, f))
            for f in os.listdir(stackoverflow_dir)
            if f.endswith(".7z")
        )
        category_sizes.append(("stackoverflow", stackoverflow_size * 7))

    category_sizes.sort(key=lambda x: x[1], reverse=True)

    # Create batches
    batches = []
    current_batch = []
    current_batch_size = 0
    for category, size in category_sizes:
        if current_batch_size + size > max_disk_usage_gb or len(current_batch) > 4:
            batches.append(current_batch)
            current_batch = []
            current_batch_size = 0
        current_batch.append(category)
        current_batch_size += size
    if current_batch:
        batches.append(current_batch)

    # Process batches
    for batch_num, batch in enumerate(batches, 1):
        command_file.append(f"echo 'Starting batch {batch_num}...'\n")

        for category in batch:
            src_category_dir = os.path.join(src_data_folder, category)
            dst_category_dir = os.path.join(dst_data_folder, category)
            processed_posts_dir = os.path.join(dst_category_dir, "processed_posts")
            processed_vote_file = os.path.join(dst_category_dir, "votes.json")
            processed_history_dir = os.path.join(
                dst_category_dir, "processed_post_history"
            )
            monthly_snapshots_dir = os.path.join(dst_category_dir, "monthly_snapshots")
            monthly_snapshots_mc_dir = os.path.join(
                dst_category_dir, "monthly_snapshots_mc"
            )
            llm_foundry_dir = f"{monthly_snapshots_mc_dir}_llm_foundry_format"

            command_file.append(f"# Processing {category}\n")
            command_file.append("(\n")  # Start of subshell for parallel execution

            # Create category directory in destination folder
            command_file.append(f"mkdir -p '{dst_category_dir}'\n")

            # Extract 7z files
            if category.lower() == "stackoverflow":
                command_file.append(
                    f"7z x '{src_category_dir}/stackoverflow.com-Posts.7z' -o'{dst_category_dir}'\n"
                )
                command_file.append(
                    f"7z x '{src_category_dir}/stackoverflow.com-PostHistory.7z' -o'{dst_category_dir}'\n"
                )
            else:
                command_file.append(
                    f"7z x '{src_category_dir}/{category}.stackexchange.com.7z' -o'{dst_category_dir}'\n"
                )

            # Process Posts.xml
            command_file.append(f"mkdir -p '{processed_posts_dir}'\n")
            command_file.append(
                f"python stackexchange_xml_to_jsonl.py --input_xml '{dst_category_dir}/Posts.xml' -o '{processed_posts_dir}'\n"
            )
            command_file.append(
                f"python get_votes.py '{dst_category_dir}/Posts.xml' --output_json '{processed_vote_file}'\n"
            )

            # Process PostHistory.xml
            command_file.append(f"mkdir -p '{processed_history_dir}'\n")
            command_file.append(
                f"python process_post_history_multiprocess.py --input_file '{dst_category_dir}/PostHistory.xml' --output_dir '{processed_history_dir}'\n"
            )

            command_file.append(f"mkdir -p '{monthly_snapshots_mc_dir}'\n")
            command_file.append(
                f"python create_monthly_snapshots_accepted_answers.py --input_path '{processed_posts_dir}' --post_history_path '{processed_history_dir}' --output_path '{monthly_snapshots_mc_dir}'\n"
            )
            command_file.append(
                f"aws s3 cp '{monthly_snapshots_mc_dir}' '{s3_path}/{category}/monthly_snapshots_mc' --recursive\n"
            )

            command_file.append(
                f"python format_qa_pairs_with_votes.py --input-dir '{monthly_snapshots_mc_dir}' --votes-file '{processed_vote_file}'\n"
            )
            command_file.append(
                f"aws s3 cp '{llm_foundry_dir}/{category}/' '{s3_path}/{category}/' --recursive\n"
            )

            # Clean up local files
            command_file.append(f"rm -rf '{dst_category_dir}'\n")

            command_file.append(") &\n")  # End of subshell, run in background

        # Wait for all processes in this batch to complete
        command_file.append("wait\n")
        command_file.append(f"echo 'Batch {batch_num} complete.'\n\n")

    command_file.append("echo 'All processing complete.'\n")

    # Write commands to bash script
    with open(output_file, "w") as f:
        f.writelines(command_file)

    print(f"Bash script generated: {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract changed and unchanged part of two consequtive wikipedia processed dumps"
    )
    parser.add_argument("--src-data", help="Local path to src_data containing StackExchange categories.", default="src_data")
    parser.add_argument("--dst-data", help="Local path to parsed StackExchange data.", default="parsed_stackexchange_data")
    parser.add_argument("--s3-path", help="S3 path to upload parsed StackExchange data. (e.g., s3://bucket/prefix/tic-lm/eval_data/stackexchange)")
    parser.add_argument("--output-file", help="Name of process script.", default="process_stackexchange_dumps.sh")
    args = parser.parse_args()

    s3_path = args.s3_path.rstrip('/')
    max_ram_usage_gb = (
        psutil.virtual_memory().total / (1024**3) * 0.75
    )  # 75% of total RAM
    max_disk_usage_gb = 300  # Example: 1TB, adjust as needed

    generate_bash_script(
        args.src_data,
        args.dst_data,
        s3_path,
        args.output_file,
        max_ram_usage_gb,
        max_disk_usage_gb,
    )
