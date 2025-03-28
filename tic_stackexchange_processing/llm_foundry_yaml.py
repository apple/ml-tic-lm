# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

"""
Module for generating YAML configuration files for StackExchange data evaluation in LLM-Foundry format.
"""
import argparse
import os
from collections import OrderedDict

import yaml

top_10_categories = set(
    [
        "stackoverflow",
        "math",
        "electronics",
        "worldbuilding",
        "unix",
        "softwareengineering",
        "english",
        "rpg",
        "codereview",
        "stats",
    ]
)


def generate_yaml_config(input_dir, output_file):
    yaml_data = OrderedDict({"icl_tasks": []})

    # Get all categories (subdirectories)
    categories = sorted(
        [d for d in os.listdir(input_dir) if os.path.isdir(os.path.join(input_dir, d))]
    )

    for category in categories:
        if category not in top_10_categories:
            continue
        category_path = os.path.join(input_dir, category)
        files = sorted([f for f in os.listdir(category_path) if f.endswith(".jsonl")])

        for file in files:
            date_range = file.split(".")[0]  # Remove file extension
            start_date, end_date = date_range.split("-")

            entry = OrderedDict(
                {
                    "label": f"{category}_{start_date}_{end_date}",
                    "dataset_uri": os.path.join(
                        "local_data/stackexchange", category, file
                    ),
                    "num_fewshot": [0],
                    # 'batch_size': 4,
                    "icl_task_type": "multiple_choice",
                    "metric_names": [
                        "InContextLearningMultipleChoiceAccuracy",
                        "InContextLearningGoldPerplexityMetric",
                    ],
                    "prompt_string": "",
                    "continuation_delimiter": "\nAnswer: ",
                }
            )
            yaml_data["icl_tasks"].append(entry)

    # Custom YAML dumper to maintain order and format lists
    class OrderedDumper(yaml.Dumper):
        def increase_indent(self, flow=False, indentless=False):
            return super(OrderedDumper, self).increase_indent(flow, False)

    def dict_representer(dumper, data):
        return dumper.represent_mapping("tag:yaml.org,2002:map", data.items())

    OrderedDumper.add_representer(OrderedDict, dict_representer)

    # Write the YAML data to file
    with open(output_file, "w") as f:
        yaml.dump(
            yaml_data, f, Dumper=OrderedDumper, default_flow_style=False, width=1000
        )

    # Post-process the file to add comments and adjust spacing
    with open(output_file, "r") as f:
        lines = f.readlines()

    processed_lines = ["icl_tasks:\n"]
    current_category = None

    for line in lines[1:]:  # Skip the first 'icl_tasks:' line
        if line.strip().startswith("label:"):
            category = line.split("_")[0].split(":")[1].strip()
            if category != current_category:
                if current_category is not None:
                    processed_lines.append("\n")  # Add a blank line between categories
                processed_lines.append(f"# {category} category\n")
                current_category = category
        processed_lines.append(line)

    with open(output_file, "w") as f:
        f.writelines(processed_lines)

    print(f"YAML configuration has been generated in '{output_file}'")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate YAML configuration for Stack Exchange data evaluation."
    )
    parser.add_argument(
        "input_dir",
        help="Path to the directory containing Stack Exchange data categories",
    )
    parser.add_argument(
        "--output_file",
        default="stackexchange_eval_config.yaml",
        help="Output YAML file name",
    )
    args = parser.parse_args()

    generate_yaml_config(args.input_dir, args.output_file)
