# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

import argparse
import json
import re
import subprocess
from datetime import datetime

import boto3

# Define the S3 buckets and paths
base_path = "s3://tic-lm/eval_data/"
buckets = {
    "raw": base_path + "temporal_wikidata_compressed/",
    "processed": base_path + "temporal_wikidata_compressed_processed/",
    "monthly": base_path + "temporal_wikidata_KG_v2/monthly/",
    "diffs": base_path + "temporal_wikidata_KG_v2/consecutive_month_diffs/",
}


def load_matching_intervals(file_path):
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: The file {file_path} was not found.")
        return {}
    except json.JSONDecodeError:
        print(f"Error: The file {file_path} is not a valid JSON file.")
        return {}


matching_intervals = load_matching_intervals("wikidata/matching_intervals.json")


def extract_date_from_filename(filename, pattern):
    match = pattern.search(filename)
    if match:
        if len(match.groups()) == 2:
            return f"{match.group(1)}_{match.group(2)}"
        return match.group(1)
    return None


def get_dates_from_s3_listing(bucket_path, pattern):
    compiled_pattern = re.compile(pattern)
    result = subprocess.run(
        ["aws", "s3", "ls", bucket_path], capture_output=True, text=True
    )
    lines = result.stdout.splitlines()
    dates = {
        extract_date_from_filename(line, compiled_pattern)
        for line in lines
        if extract_date_from_filename(line, compiled_pattern)
    }
    return sorted(dates)


date_patterns = {
    "raw": r"wikidatawiki-(\d{8})-pages-articles",
    "processed": r"wikidata-(\d{8})\.json",
    "monthly": r"PRE (\d{8})/",
    "diffs": r"PRE (\d{8})_(\d{8})/",
}


def main(min_date=None, num_diffs=None):
    raw_dates = get_dates_from_s3_listing(buckets["raw"], date_patterns["raw"])
    raw_dates = sorted(set(raw_dates) - set(["20150307", "20150806"]))
    processed_dates = get_dates_from_s3_listing(
        buckets["processed"], date_patterns["processed"]
    )
    monthly_dates = get_dates_from_s3_listing(
        buckets["monthly"], date_patterns["monthly"]
    )
    diff_dates = get_dates_from_s3_listing(buckets["diffs"], date_patterns["diffs"])

    expected_diffs = {
        f"{date}_{next_date}" for date, next_date in zip(raw_dates[:-1], raw_dates[1:])
    }
    missing_diffs = sorted(expected_diffs - set(diff_dates))

    if min_date:
        missing_diffs = [
            diff for diff in missing_diffs if diff.split("_")[0] >= min_date
        ]

    if num_diffs is not None:
        missing_diffs = missing_diffs[:num_diffs]

    script_lines = [
        "#!/bin/bash",
        "",
        "# Install GNU Parallel if not already installed",
        # "sudo apt-get update && sudo apt-get install -y parallel",
        "# Stage 1: Process raw data",
        "echo 'Downloading and processing raw data...'",
    ]

    raw_to_process = set()
    for date_range in missing_diffs:
        old_date, new_date = date_range.split("_")
        if old_date not in processed_dates:
            raw_to_process.add(old_date)
        if new_date not in processed_dates:
            raw_to_process.add(new_date)

    for date in sorted(raw_to_process):
        script_lines.append(
            f"aws s3 cp {buckets['raw']}wikidatawiki-{date}-pages-articles-multistream.xml.bz2 wikidatawiki-{date}-pages-articles-multistream.xml.bz2"
        )

    script_lines.append("")
    script_lines.append("# Process raw files in parallel")
    for date in sorted(raw_to_process):
        script_lines.append(
            f"python -m gensim.scripts.segment_wiki -i -f wikidatawiki-{date}-pages-articles-multistream.xml.bz2 -o Wikidata_datasets/wikidata-{date}.json.gz &"
        )

    script_lines.append("wait  # Wait for all background processes to finish")

    script_lines.append("")
    script_lines.append("# Upload processed files")
    for date in sorted(raw_to_process):
        script_lines.append(
            f"aws s3 cp Wikidata_datasets/wikidata-{date}.json.gz {buckets['processed']}wikidata-{date}.json.gz"
        )

    script_lines.extend(
        [
            "",
            "# Stage 2: Ensure monthly data is available locally or generate it",
            "echo 'Ensuring monthly data is available or generating it...'",
        ]
    )

    monthly_to_ensure = set()
    monthly_to_generate = set()
    for date_range in missing_diffs:
        old_date, new_date = date_range.split("_")
        if old_date in monthly_dates:
            monthly_to_ensure.add(old_date)
        else:
            monthly_to_generate.add(old_date)
        if new_date in monthly_dates:
            monthly_to_ensure.add(new_date)
        else:
            monthly_to_generate.add(new_date)

    for date in sorted(monthly_to_ensure):
        script_lines.append(
            f"aws s3 cp {buckets['monthly']}{date}/ Wikidata_datasets/{date} --recursive"
        )

    script_lines.extend(
        [
            "",
            "# Download processed data for generating missing monthly data",
            "echo 'Downloading processed data for missing monthly data generation...'",
        ]
    )

    for date in sorted(monthly_to_generate):
        script_lines.append(
            f"aws s3 cp {buckets['processed']}wikidata-{date}.json.gz Wikidata_datasets/wikidata-{date}.json.gz"
        )

    script_lines.extend(
        [
            "",
            "# Generate missing monthly data",
            "echo 'Generating missing monthly data...'",
        ]
    )

    for date in sorted(monthly_to_generate):
        script_lines.append(f"python wikidata_datasets_ind.py --old {date} &")

    script_lines.append("wait  # Wait for all background processes to finish")

    # Upload generated monthly data
    for date in sorted(monthly_to_generate):
        script_lines.append(
            f"aws s3 cp Wikidata_datasets/{date} {buckets['monthly']}{date}/ --recursive"
        )

    script_lines.extend(["", "# Stage 3: Process diffs", "echo 'Processing diffs...'"])

    for date_range in missing_diffs:
        old_date, new_date = date_range.split("_")
        script_lines.extend(
            [
                f"python wikidata_processor_distributed.py --old {old_date} --new {new_date}",
                f"aws s3 cp Wikidata_datasets/{old_date}_{new_date} {buckets['diffs']}{old_date}_{new_date}/ --recursive",
            ]
        )

    script_lines.append("")
    script_lines.extend(
        [
            "",
            "# Stage 4: Further consecutive month processing",
            "echo 'Performing further consecutive month processing...'",
        ]
    )

    # Download diff and unchanged files
    for wikidata_range in missing_diffs:
        old_date_wikidata, new_date_wikidata = wikidata_range.split("_")
        wikidata_key = f"{old_date_wikidata}-{new_date_wikidata}"
        if wikidata_key in matching_intervals:
            wikipedia_range = matching_intervals[wikidata_key]
            old_date_wiki, new_date_wiki = wikipedia_range.split("-")

            script_lines.extend(
                [
                    f"aws s3 cp s3://tic-lm/eval_data/diffset_changed_wiki_v2/wiki_diff_{new_date_wiki}_{old_date_wiki}.csv Wikipedia_datasets/wiki_diff_{new_date_wiki}_{old_date_wiki}.csv &",
                ]
            )

    script_lines.append("wait")

    # Run aligning_wikipedia_wikidata.py for each date range
    for wikidata_range in missing_diffs:
        old_date_wikidata, new_date_wikidata = wikidata_range.split("_")
        wikidata_key = f"{old_date_wikidata}-{new_date_wikidata}"
        if wikidata_key in matching_intervals:
            wikipedia_range = matching_intervals[wikidata_key]
            old_date_wiki, new_date_wiki = wikipedia_range.split("-")
            script_lines.append(
                f"python aligning_wikipedia_wikidata.py --old {old_date_wikidata} --new {new_date_wikidata}  --mode changed &"
            )

    script_lines.append("wait")

    # Upload processed diffs to S3
    for wikidata_range in missing_diffs:
        old_date, new_date = wikidata_range.split("_")
        script_lines.append(
            f"aws s3 cp Wikidata_datasets/{old_date}_{new_date} s3://tic-lm/eval_data/temporal_wikidata_KG_v2/consecutive_month_diffs/{old_date}_{new_date}/ --recursive &"
        )

    script_lines.append("wait")

    script_lines.append("")
    script_lines.append("echo 'All processing completed.'")

    with open("process_missing_diffs.sh", "w") as file:
        file.write("\n".join(script_lines))

    print("Bash script 'process_missing_diffs.sh' has been created.")

    print(f"Raw dates: {raw_dates}")
    print(f"Processed dates: {processed_dates}")
    print(f"Monthly dates: {monthly_dates}")
    print(f"Diff dates: {diff_dates}")
    print(f"Missing diffs to process: {missing_diffs}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate script for processing missing diffs."
    )
    parser.add_argument(
        "--min_date", type=str, help="Minimum date to process (YYYYMMDD format)"
    )
    parser.add_argument(
        "--num_diffs", type=int, help="Number of missing diffs to process"
    )
    args = parser.parse_args()

    main(min_date=args.min_date, num_diffs=args.num_diffs)
