# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

import argparse
import os
import re
from datetime import datetime

import boto3


def process_dumps(bucket, prefix, num_processes):
    # List files from S3
    files = list_files(bucket, prefix)

    # Filter files based on the existence of the output directory
    filtered_files = []
    for file_key in files:
        date_part = extract_date_from_filename(file_key)
        if date_part:
            output_dir = date_part.strftime("%Y%m%d")
            if not os.path.exists(output_dir):
                filtered_files.append(file_key)

    # Prepare the script with setup and initial commands
    script_lines = ["#!/bin/bash\n\n"]

    # Process files in batches of 6, respecting the exclusion logic
    for i in range(0, len(filtered_files), 12):
        batch_files = filtered_files[i : i + 12]

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
            output_dir = date_part.strftime("%Y%m%d")
            file_name = file_key.split("/")[-1]
            script_lines.append(
                f"mkdir -p {output_dir} && python -m wikiextractor.WikiExtractor {file_name} --processes {num_processes} --json --output {output_dir} &\n"
            )
        script_lines.append("wait\n")

        # Cleanup commands
        script_lines.append("\n# Cleaning up downloaded files\n")
        for file_key in batch_files:
            file_name = file_key.split("/")[-1]
            date_part = extract_date_from_filename(file_key)
            output_dir = date_part.strftime("%Y%m%d")
            script_lines.append(f"rm -rf {file_name} &\n")
        script_lines.append("wait\n\n")

        # Compression commands
        script_lines.append("\n# Compressing directories\n")
        for file_key in batch_files:
            date_part = extract_date_from_filename(file_key)
            output_dir = date_part.strftime("%Y%m%d")
            script_lines.append(
                f"tar -I zstd -cvf {output_dir}.tar.zstd {output_dir}/ &\n"
            )
        script_lines.append("wait\n")

        # Upload to S3
        script_lines.append("\n# Uploading compressed files to S3\n")
        for file_key in batch_files:
            date_part = extract_date_from_filename(file_key)
            output_dir = date_part.strftime("%Y%m%d")
            script_lines.append(
                f"aws s3 cp {output_dir}.tar.zstd s3://{bucket}/{'/'.join(prefix.split('/')[:-1])}/temporal_wikipedia_processed_compressed/{output_dir}.tar.zstd &\n"
            )
        script_lines.append("wait\n")

        # Cleanup commands
        script_lines.append("\n# Cleaning up files\n")
        for file_key in batch_files:
            file_name = file_key.split("/")[-1]
            date_part = extract_date_from_filename(file_key)
            output_dir = date_part.strftime("%Y%m%d")
            script_lines.append(f"rm -rf {output_dir}/ {output_dir}.tar.zstd &\n")
        script_lines.append("wait\n\n")

    # Final message
    script_lines.append('echo "All processes have completed."\n')

    # Write the commands to a bash script
    with open("process_dumps.sh", "w") as bash_script:
        bash_script.writelines(script_lines)


def list_files(bucket, prefix):
    """List all files in the given S3 bucket and prefix."""
    s3 = boto3.client("s3")
    response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    files = [
        item["Key"]
        for item in response.get("Contents", [])
        if item["Key"].endswith(".bz2")
    ]
    return files


def extract_date_from_filename(filename):
    """Extract the date from the filename."""
    pattern = re.compile(r"enwiki-(\d{8})-pages-articles-multistream.xml.bz2$")
    match = pattern.search(filename)
    if match:
        return datetime.strptime(match.group(1), "%Y%m%d")
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Process Wikipedia dumps using WikiExtractor"
    )

    parser.add_argument("--s3-path", help="S3 path to Wikipedia XML dumps (e.g., s3://bucket/prefix)")

    parser.add_argument(
        "--num-processes",
        type=int,
        default=60,
        help="Number of parallel processes to use (default: 60)",
    )
    args = parser.parse_args()

    s3_path_parts = args.s3_path.replace("s3://", "").split("/", 1)
    bucket_name = s3_path_parts[0]
    prefix = s3_path_parts[1] if len(s3_path_parts) > 1 else ""

    process_dumps(bucket_name, prefix, args.num_processes)
