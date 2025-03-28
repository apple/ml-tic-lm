# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

"""
Module for processing JSONL files to create two-choice question format with gold answer and one random choice.
"""

import argparse
import json
import os
import random
import sys


def process_jsonl(input_file, output_file):
    with open(input_file, "r") as infile, open(output_file, "w") as outfile:
        for line in infile:
            data = json.loads(line)

            choices = data["choices"]
            gold_index = data["gold"]

            gold_choice = choices[gold_index]
            other_choices = [
                choice for i, choice in enumerate(choices) if i != gold_index
            ]
            random_choice = random.choice(other_choices)

            new_choices = [gold_choice, random_choice]
            random.shuffle(new_choices)

            new_gold_index = new_choices.index(gold_choice)

            data["choices"] = new_choices
            data["gold"] = new_gold_index

            json.dump(data, outfile)
            outfile.write("\n")


def process_directory(input_dir, output_dir):
    for root, dirs, files in os.walk(input_dir):
        for file in files:
            if file.endswith(".jsonl"):
                input_path = os.path.join(root, file)
                relative_path = os.path.relpath(input_path, input_dir)
                output_path = os.path.join(output_dir, relative_path)

                os.makedirs(os.path.dirname(output_path), exist_ok=True)

                process_jsonl(input_path, output_path)
                print(f"Processed {input_path} -> {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Process JSONL files to keep gold choice and one random choice."
    )
    parser.add_argument("input_dir", help="Input directory containing JSONL files")
    parser.add_argument(
        "--suffix",
        default="_2choices",
        help="Suffix to prepend to the output directory name (default: _2choice)",
    )

    args = parser.parse_args()

    input_dir = args.input_dir
    suffix = args.suffix

    if not os.path.isdir(input_dir):
        print(f"Error: {input_dir} is not a valid directory")
        sys.exit(1)

    # Create output directory name by prepending the suffix
    input_dir_name = os.path.basename(os.path.normpath(input_dir))
    output_dir_name = f"{input_dir_name}{suffix}"
    output_dir = os.path.join(os.path.dirname(input_dir), output_dir_name)

    process_directory(input_dir, output_dir)
    print(f"Processed all files from {input_dir}")
    print(f"Output saved in {output_dir}")


if __name__ == "__main__":
    main()
