# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

import json
import os
import re
from datetime import datetime

import boto3

MAX_CONCURRENT = 5

corrupted_files = set(["wikidatawiki-20150307-pages-articles-multistream.xml.bz2"])
set_processed_months = set()


# Function to add commands for processing a pair of dates
def add_date_processing_commands(old_date, new_date):
    process_cmd = []
    old_date_str = old_date.strftime("%Y%m%d")
    new_date_str = new_date.strftime("%Y%m%d")
    process_cmd.append(
        f"python wikidata_processor_distributed.py --old {old_date_str} --new {new_date_str} && "
    )
    if old_date_str not in set_processed_months:
        process_cmd.append(
            f"aws s3 cp Wikidata_datasets/{old_date_str} s3://tic-lm/eval_data/temporal_wikidata_KG_v2/monthly/{old_date_str}/ --recursive && "
        )
        set_processed_months.add(old_date_str)
    if new_date_str not in set_processed_months:
        process_cmd.append(
            f"aws s3 cp Wikidata_datasets/{new_date_str} s3://tic-lm/eval_data/temporal_wikidata_KG_v2/monthly/{new_date_str}/ --recursive && "
        )
        set_processed_months.add(new_date_str)
    process_cmd.append(
        f"aws s3 cp Wikidata_datasets/{old_date_str}_{new_date_str} s3://tic-lm/eval_data/temporal_wikidata_KG_v2/consecutive_month_diffs/{old_date_str}_{new_date_str}/ --recursive &\n"
    )
    return process_cmd


def add_wikipedia_algining_commands(date_parts):

    process_cmd = []
    with open("wikidata/matching_intervals.json", "r") as file:
        date_mapping = json.load(file)

    modes = ["changed", "unchanged"]

    for i in range(0, len(date_parts) - 1):
        old_date, new_date = date_parts[i], date_parts[i + 1]
        old, new = old_date.strftime("%Y%m%d"), new_date.strftime("%Y%m%d")
        wikidata_range = f"{old}-{new}"
        wikipedia_range = date_mapping[wikidata_range]
        wikipedia_start, wikipedia_end = wikipedia_range.split("-")

        for mode in modes:
            if mode == "changed":
                process_cmd.append(
                    f"aws s3 cp s3://tic-lm/eval_data/diffset_changed_wiki_v2/wiki_diff_{wikipedia_end}_{wikipedia_start}.csv Wikipedia_datasets/wiki_diff_{wikipedia_end}_{wikipedia_start}.csv &\n"
                )
            else:
                process_cmd.append(
                    f"aws s3 cp s3://tic-lm/eval_data/diffset_unchanged_wiki_v2/wiki_unchanged_{wikipedia_end}_{wikipedia_start}.csv Wikipedia_datasets/wiki_unchanged_{wikipedia_end}_{wikipedia_start}.csv &\n"
                )

    process_cmd.append("wait\n")
    for i in range(0, len(date_parts) - 1):
        old_date, new_date = date_parts[i], date_parts[i + 1]
        old, new = old_date.strftime("%Y%m%d"), new_date.strftime("%Y%m%d")
        # for mode in modes:
        process_cmd.append(
            f"python wikidata_wikipedia_aligner.py --old {old} --new {new} --mode changed &\n"
        )

    process_cmd.append("wait\n")

    for i in range(0, len(date_parts) - 1):
        old_date, new_date = date_parts[i], date_parts[i + 1]
        old_date_str, new_date_str = old_date.strftime("%Y%m%d"), new_date.strftime(
            "%Y%m%d"
        )
        process_cmd.append(
            f"aws s3 cp Wikidata_datasets/{old_date_str}_{new_date_str} s3://tic-lm/eval_data/temporal_wikidata_KG_v2/consecutive_month_diffs/{old_date_str}_{new_date_str}/ --recursive &\n"
        )

    process_cmd.append("wait\n")
    return process_cmd


def remove_local_files_not_needed(processed_months):
    processed_months = [month.strftime("%Y%m%d") for month in processed_months]
    # Sort processed months to determine the latest one
    sorted_months = sorted(processed_months)
    if sorted_months:
        # Generate removal commands for all but the latest month's files
        removal_commands = []
        for i in range(len(sorted_months) - 1):  # Adjust to stop before the last month
            current_month = sorted_months[i]
            next_month = sorted_months[i + 1]
            month_command = f"rm -rf Wikidata_datasets/{current_month}/ &\n"
            removal_commands.append(month_command)
            removal_commands.append(
                f"rm -rf Wikidata_datasets/wikidata-{current_month}.json.gz &\n"
            )
            # Generate commands to remove diff files between consecutive months
            diff_data_command = (
                f"rm -rf Wikidata_datasets/{current_month}_{next_month}/ &\n"
            )
            removal_commands.append(diff_data_command)
        removal_commands.append("rm -rf Wikipedia_datasets/ &\n")
        # removal_commands.append("\n echo 'Wait for all removals to be done'\n")
        removal_commands.append("wait\n")

        return removal_commands


def generate_bash_script_for_main_process(files):

    # Extract and store date parts for sequence handling
    date_parts = [
        extract_date_from_filename(file_key)
        for file_key in files
        if extract_date_from_filename(file_key)
    ]
    process_cmd = []

    # Define batches for non-overlapping and overlapping date sequences
    non_overlapping_batches = []
    overlapping_batches = []

    i = 0
    while i < len(date_parts) - 1:
        non_overlapping_batches.append((date_parts[i], date_parts[i + 1]))
        if i + 2 < len(date_parts):
            overlapping_batches.append((date_parts[i + 1], date_parts[i + 2]))
        i += 2

    # Process non-overlapping batches
    for old_date, new_date in non_overlapping_batches:
        process_cmd.extend(add_date_processing_commands(old_date, new_date))

    process_cmd.append(
        "\n# Wait for non-overlapping batches to complete before starting overlapping batches\n"
    )
    process_cmd.append("wait\n")

    # Process overlapping batches
    for old_date, new_date in overlapping_batches:
        process_cmd.extend(add_date_processing_commands(old_date, new_date))
    process_cmd.append("wait\n")

    process_cmd.extend(add_wikipedia_algining_commands(date_parts))
    # Final message
    process_cmd.append('echo "All processes have completed."\n')

    process_cmd.extend(remove_local_files_not_needed(date_parts))
    process_cmd.append('echo "Local processesed files have been removed."\n')

    return process_cmd


def generate_bash_script_for_commands(
    bucket, prefix, size_threshold=250 * 1024**3, min_date_str="20171120"
):  # size_threshold in bytes
    # List files and their sizes from S3
    files = list_files(bucket, prefix)
    print(files)
    files = filter_filenames_by_date(files, min_date_str)
    # Filter files based on the existence of the output directory and calculate batches
    filtered_files = []
    current_batch = []
    current_size = 0

    for file_key, file_size in files:
        if file_key.split("/")[-1] in corrupted_files:
            continue
        date_part = extract_date_from_filename(file_key)
        if date_part:
            output_dir = date_part.strftime("%Y%m%d")
            if not os.path.exists(output_dir):
                if (
                    current_size + file_size <= size_threshold
                    and len(current_batch) < MAX_CONCURRENT
                ):
                    current_batch.append(file_key)
                    current_size += file_size
                else:
                    filtered_files.append(current_batch)
                    current_batch = [file_key]
                    current_size = file_size
    if current_batch:
        filtered_files.append(current_batch)

    # Prepare the script with setup and initial commands
    script_lines = ["#!/bin/bash\n\n"]

    # Process files respecting the size limit
    for idx_batch, batch_files in enumerate(filtered_files):

        # Download commands
        script_lines.append("# Downloading files\n")
        for file_key in batch_files:
            file_name = file_key.split("/")[-1]
            script_lines.append(f"aws s3 cp s3://{bucket}/{file_key} {file_name} &\n")
        script_lines.append("wait\n")

        # Extract commands
        script_lines.append("\n# Extracting files\n")
        for file_key in batch_files:
            date_part = extract_date_from_filename(file_key)
            date_wiki = date_part.strftime("%Y%m%d")
            file_name = file_key.split("/")[-1]
            script_lines.append(
                f"python -m gensim.scripts.segment_wiki -i -f {file_name} -o Wikidata_datasets/wikidata-{date_wiki}.json.gz && aws s3 cp Wikidata_datasets/wikidata-{date_wiki}.json.gz s3://tic-lm/eval_data/temporal_wikidata_compressed_processed/wikidata-{date_wiki}.json.gz &\n"
            )
        script_lines.append("wait\n")

        # Cleanup commands
        script_lines.append("\n# Cleaning up files\n")
        for file_key in batch_files:
            file_name = file_key.split("/")[-1]
            script_lines.append(f"rm -rf {file_name} &\n")
        script_lines.append("wait\n\n")

        process_files = (
            [filtered_files[idx_batch - 1][-1]] + batch_files
            if idx_batch
            else batch_files
        )
        script_lines.extend(generate_bash_script_for_main_process(process_files))

    # Final message
    script_lines.append('echo "All processes have completed."\n')

    # Write the commands to a bash script
    with open("batched_wikidata_script.sh", "w") as bash_script:
        bash_script.writelines(script_lines)


def list_files(bucket, prefix):
    """List all files in the given S3 bucket and prefix with their sizes."""
    s3 = boto3.client("s3")
    response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    files = [
        (item["Key"], item["Size"])
        for item in response.get("Contents", [])
        if item["Key"].endswith(".bz2")
    ]
    return files


def extract_date_from_filename(filename):
    """Extract the date from the filename."""
    pattern = re.compile(r"wikidatawiki-(\d{8})-pages-articles-multistream.xml.bz2$")
    match = pattern.search(filename)
    if match:
        return datetime.strptime(match.group(1), "%Y%m%d")
    return None


def filter_filenames_by_date(filenames, min_date_str, max_num_outputs=200):
    """
    Filter filenames based on a minimum date and limit the number of outputs.
    """
    # Convert min_date_str to datetime for comparison
    min_date = datetime.strptime(min_date_str, "%Y%m%d")

    # Extract dates and filter
    dated_filenames = []
    for filename in filenames:
        date = extract_date_from_filename(filename[0])
        if date and date > min_date:
            dated_filenames.append((date, filename))

    # Sort by date
    dated_filenames.sort()

    # Select the filenames from the sorted list, limited by max_num_outputs
    filtered_filenames = [filename for _, filename in dated_filenames[:max_num_outputs]]

    return filtered_filenames


if __name__ == "__main__":
    bucket = "<YOUR_BUCKET>"
    prefix = "<YOUR_PREFIX>"
    generate_bash_script_for_commands(bucket, prefix)
