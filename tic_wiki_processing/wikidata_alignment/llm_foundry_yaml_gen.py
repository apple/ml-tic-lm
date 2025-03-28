# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

import json
from collections import OrderedDict

import yaml


def ordered_dict_representer(dumper, data):
    return dumper.represent_mapping("tag:yaml.org,2002:map", data.items())


yaml.add_representer(OrderedDict, ordered_dict_representer)


def generate_yaml_config(input_file, output_prefix):
    with open(input_file, "r") as f:
        date_ranges = json.load(f)

    yaml_data_both = {"icl_tasks": []}
    yaml_data_object = {"icl_tasks": []}

    for date_range in date_ranges:
        base_entry = OrderedDict(
            [
                ("label", f"{date_range}"),
                ("dataset_uri", ""),
                ("num_fewshot", [0]),
                ("icl_task_type", "generation_task_with_answers"),
                ("metric_names", ["InContextLearningGenerationExactMatchAccuracy"]),
                ("prompt_string", ""),
                ("continuation_delimiter", " "),
            ]
        )

        entry_both = base_entry.copy()
        entry_both["label"] += "_both"
        entry_both["dataset_uri"] = f"local_data/wikidata_qa/{date_range}_both.jsonl"
        yaml_data_both["icl_tasks"].append(entry_both)

        entry_object = base_entry.copy()
        entry_object["label"] += "_object"
        entry_object["dataset_uri"] = (
            f"local_data/wikidata_qa/{date_range}_object.jsonl"
        )
        yaml_data_object["icl_tasks"].append(entry_object)

    for suffix in ["both", "object"]:
        output_file = f"{output_prefix}_{suffix}.yaml"
        with open(output_file, "w") as f:
            yaml.dump(
                yaml_data_both if suffix == "both" else yaml_data_object,
                f,
                default_flow_style=False,
                sort_keys=False,
            )

        # Add spaces between tasks
        with open(output_file, "r") as f:
            content = f.read()
        content = content.replace("- label:", "\n- label:")
        with open(output_file, "w") as f:
            f.write(content)

        print(f"YAML configuration has been generated in '{output_file}'")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate YAML configurations for LLM evaluation."
    )
    parser.add_argument(
        "input_file", help="Path to the JSON file containing date ranges"
    )
    parser.add_argument(
        "--output_prefix",
        default="eval_config_wikidata",
        help="Prefix for output YAML files",
    )
    args = parser.parse_args()

    generate_yaml_config(args.input_file, args.output_prefix)
