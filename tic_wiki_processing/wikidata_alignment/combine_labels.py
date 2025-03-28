# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

import argparse
import json
import os


def parse_args():
    parser = argparse.ArgumentParser(
        description="Combine JSONL label files into a single JSON mapping file"
    )
    parser.add_argument(
        "--input-dir", required=True, help="Directory containing JSONL label files"
    )
    parser.add_argument(
        "--output-dir", required=True, help="Directory to save the combined JSON file"
    )
    return parser.parse_args()


def combine_label_files(input_dir, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    all_data = {}
    num_files = 0

    # Process each JSONL file
    for filename in os.listdir(input_dir):
        if filename.endswith(".jsonl") and "label" in filename:
            try:
                with open(os.path.join(input_dir, filename), "r") as file:
                    for line in file:
                        data = json.loads(line)
                        all_data.update(data)
                num_files += 1
                if num_files % 10 == 0:
                    print(f"Processed {num_files} files...")
            except Exception as e:
                print(f"Error processing file {filename}: {e}")
                continue

    # Save combined data
    output_file = os.path.join(output_dir, "all_id_to_label.json")
    with open(output_file, "w") as f:
        json.dump(all_data, f)
    print(f"Successfully combined {num_files} files into {output_file}")


if __name__ == "__main__":
    args = parse_args()
    combine_label_files(args.input_dir, args.output_dir)
