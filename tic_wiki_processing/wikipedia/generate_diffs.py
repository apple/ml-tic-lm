# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

import argparse
import re
import os
from datetime import datetime

import boto3

# Initialize a boto3 client
s3 = boto3.client("s3")


def list_files(bucket, prefix):
    """List all files in the given S3 bucket and prefix."""
    response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    files = [item["Key"] for item in response.get("Contents", [])]
    return files


def extract_dates(files):
    """Extract dates from file names and return them sorted."""
    date_pattern = re.compile(r"(\d{8}).tar.zstd")
    dates = [
        datetime.strptime(date_pattern.search(file).group(1), "%Y%m%d")
        for file in files
        if date_pattern.search(file)
    ]
    return sorted(dates)


concurrent_proc = 4


def diffsets_bash_script(dates, output_path, bucket_name, prefix):
    """Generate a bash script with commands for each batch of dates."""
    # Extract the base path from the input prefix
    base_path = os.path.dirname(prefix.rstrip('/'))
    if base_path:
        base_path += '/'
    
    # Define output directories using the base path
    changed_wiki_dir = f"{base_path}diffest_changed_wiki/"
    unchanged_wiki_dir = f"{base_path}diffest_unchanged_wiki/"
    
    with open(output_path, "w") as script_file:

        len_dates = len(dates)
        last_date_str = None

        for batch_start in range(0, len_dates, concurrent_proc):
            batch_end = min(batch_start + concurrent_proc, len_dates)
            current_batch = dates[batch_start:batch_end]

            # Download and extract files
            for date in current_batch:
                date_str = date.strftime("%Y%m%d")
                script_file.write(
                    f"aws s3 cp s3://{bucket_name}/{prefix}{date_str}.tar.zstd {date_str}.tar.zstd && "
                )
                script_file.write(
                    f"tar -I zstd -xvf {date_str}.tar.zstd {date_str}/ && rm -rf {date_str}.tar.zstd &\n"
                )
            script_file.write("\nwait\n\n")

            # Process files with consecutive dates
            if last_date_str is not None:
                old_date = last_date_str
            else:
                # For the first batch, old_date should come from the previous date if available
                old_date = current_batch[0].strftime("%Y%m%d")

            for date in current_batch:
                new_date = date.strftime("%Y%m%d")
                if (
                    old_date != new_date
                ):  # Ensure old_date and new_date are not the same
                    script_file.write(
                        f"python parse_wikipedia.py --old_month {old_date} --new_month {new_date} &\n"
                    )
                old_date = new_date
            script_file.write("\nwait\n\n")

            # Upload results and clean up
            if last_date_str is not None:
                old_date = last_date_str
            else:
                old_date = current_batch[0].strftime("%Y%m%d")

            for date in current_batch:
                new_date = date.strftime("%Y%m%d")
                if (
                    old_date != new_date
                ):  # Ensure old_date and new_date are not the same
                    # Using the parameterized output paths
                    script_file.write(
                        f"aws s3 cp wiki_diff_{new_date}_{old_date}.csv s3://{bucket_name}/{changed_wiki_dir}\n"
                    )
                    script_file.write(
                        f"aws s3 cp wiki_unchanged_{new_date}_{old_date}.csv s3://{bucket_name}/{unchanged_wiki_dir}\n"
                    )
                    script_file.write(
                        f"rm -rf wiki_diff_{new_date}_{old_date}.csv wiki_unchanged_{new_date}_{old_date}.csv &\n"
                    )
                old_date = new_date
            script_file.write("\nwait\n\n")

            # Remove processed directories, but keep the last one for the next batch
            if last_date_str:
                script_file.write(f"rm -rf {last_date_str}/ &\n")
            for date in current_batch[:-1]:
                date_str = date.strftime("%Y%m%d")
                script_file.write(f"rm -rf {date_str}/ &\n")
            script_file.write("\nwait\n\n")

            last_date_str = current_batch[-1].strftime("%Y%m%d")

        # Final cleanup for the last date directory
        script_file.write(f"rm -rf {last_date_str}/ &\n")
        script_file.write("\nwait\n\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract changed and unchanged part of two consequtive wikipedia processed dumps"
    )
    parser.add_argument("--s3-path", help="S3 path to processed Wikipedia dumps (e.g., s3://bucket/prefix)")
    args = parser.parse_args()

    s3_path_parts = args.s3_path.replace("s3://", "").split("/", 1)
    bucket_name = s3_path_parts[0]
    prefix = s3_path_parts[1] if len(s3_path_parts) > 1 else ""
    # Main process
    files = list_files(bucket_name, prefix)
    dates = extract_dates(files)
    diffsets_bash_script(dates, "diffsets_script.sh", bucket_name, prefix)

    print("Bash script generated successfully.")
