# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

import argparse
import json
import os
import random

import pandas as pd
import yaml


def sample_file(input_file, output_file, num_samples, file_type):
    if file_type == "csv":
        df = pd.read_csv(input_file)
        sampled_df = df.sample(n=min(num_samples, len(df)))

        with open(output_file, "w") as f:
            for text in sampled_df["text"]:
                json.dump({"context": text, "continuation": ""}, f)
                f.write("\n")
    else:  # JSONL
        with open(input_file, "r") as infile:
            lines = infile.readlines()

        sampled_lines = random.sample(lines, min(num_samples, len(lines)))

        with open(output_file, "w") as outfile:
            outfile.writelines(sampled_lines)

    print(f"Sampled {num_samples} lines from {input_file} to {output_file}")


def create_yaml_for_sampled_files(output_directory):
    icl_tasks = []

    jsonl_files = sorted(
        [f for f in os.listdir(output_directory) if f.endswith(".jsonl")]
    )

    for file in jsonl_files:
        task_info = {
            "label": file[:-6],
            "dataset_uri": f"l{os.path.basename(output_directory)}/{file}",
            "num_fewshot": [0],
            "num_samples": 10000,
            "icl_task_type": "language_modeling",
            "metric_names": ["LanguageNounPerplexity"],
            "has_categories": False,
        }
        icl_tasks.append(task_info)

    final_yaml_content = {"icl_tasks": icl_tasks}
    yaml_file_name = f"{os.path.basename(output_directory)}.yaml"

    # Write YAML file in the current directory
    with open(yaml_file_name, "w") as yaml_file:
        yaml.dump(final_yaml_content, yaml_file, sort_keys=False, allow_unicode=True)

    print(f"Created YAML file: {yaml_file_name} in the current directory")


def main():
    parser = argparse.ArgumentParser(
        description="Sample JSONL/CSV files and generate YAML."
    )
    parser.add_argument(
        "input_dir", type=str, help="Input directory containing JSONL/CSV files."
    )
    parser.add_argument(
        "--num_samples",
        type=int,
        default=10000,
        help="Number of lines to sample from each file.",
    )
    parser.add_argument(
        "--file_type",
        choices=["jsonl", "csv"],
        required=True,
        help="Specify input file type: jsonl or csv",
    )

    args = parser.parse_args()

    output_dir = f"{args.input_dir}_sampled"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    file_extension = ".jsonl" if args.file_type == "jsonl" else ".csv"

    for file in os.listdir(args.input_dir):
        if file.endswith(file_extension):
            input_file = os.path.join(args.input_dir, file)
            output_file = os.path.join(
                output_dir,
                file if args.file_type == "jsonl" else file.replace(".csv", ".jsonl"),
            )
            sample_file(input_file, output_file, args.num_samples, args.file_type)

    create_yaml_for_sampled_files(output_dir)

    print("Sampling and YAML generation completed successfully.")


if __name__ == "__main__":
    main()
