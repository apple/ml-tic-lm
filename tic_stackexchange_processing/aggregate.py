# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#
"""
JSONL Aggregator - Combines monthly JSONL files into aggregated files of num_lines lines each.
"""
import argparse
import glob
import os
from datetime import datetime, timedelta


def aggregate_jsonl_files(base_path, output_base_path, num_lines):
    # Get all categories (subdirectories)
    categories = [
        d for d in os.listdir(base_path) if os.path.isdir(os.path.join(base_path, d))
    ]

    for category in categories:
        category_path = os.path.join(base_path, category)
        output_category_path = os.path.join(output_base_path, category)
        os.makedirs(output_category_path, exist_ok=True)

        # Sort files based on the date in the filename
        files = sorted(
            glob.glob(os.path.join(category_path, "*.jsonl")),
            key=lambda x: datetime.strptime(os.path.basename(x).split(".")[0], "%Y-%m"),
        )

        start_file = None
        total_lines = 0
        aggregated_content = []

        for file in files:
            with open(file, "r") as f:
                content = f.readlines()

            if not start_file:
                start_file = file

            total_lines += len(content)
            aggregated_content.extend(content)

            if total_lines >= num_lines:
                # Generate output filename
                start_date = datetime.strptime(
                    os.path.basename(start_file).split(".")[0], "%Y-%m"
                )
                end_date = datetime.strptime(
                    os.path.basename(file).split(".")[0], "%Y-%m"
                )

                # Adjust end date to be the last day of the month
                end_date = (end_date.replace(day=1) + timedelta(days=32)).replace(
                    day=1
                ) - timedelta(days=1)

                output_filename = f"{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}.jsonl"

                # Write aggregated content
                output_path = os.path.join(output_category_path, output_filename)
                with open(output_path, "w") as f:
                    f.writelines(aggregated_content[:num_lines])

                print(f"Created aggregated file: {output_path}")

                # Reset for next aggregation
                start_file = None
                total_lines = 0
                aggregated_content = []


def main():
    parser = argparse.ArgumentParser(
        description="Aggregate JSONL files into chunks of 500 lines."
    )
    parser.add_argument(
        "--input-path",
        type=str,
        required=True,
        help="Base path containing category directories with JSONL files",
    )
    parser.add_argument(
        "--output-path",
        type=str,
        required=True,
        help="Output base path for aggregated JSONL files",
    )
    parser.add_argument(
        "--num-lines",
        type=int,
        default=500,
        help="Number of lines per aggregated file (default: 500)",
    )

    args = parser.parse_args()

    aggregate_jsonl_files(args.input_path, args.output_path, args.num_lines)


if __name__ == "__main__":
    main()
