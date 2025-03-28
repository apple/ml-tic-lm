# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

import argparse
import json
import os
import random
import sys
from collections import Counter


def stratified_sampling(input_file, output_file, num_samples):
    # Read the file and count relations
    relations = []
    data = []
    with open(input_file, "r", encoding="utf-8") as file:
        for line in file:
            item = json.loads(line)
            relations.append(item["metadata"]["relation"])
            data.append(item)

    relation_counts = Counter(relations)

    # Sort relations by frequency
    sorted_relations = sorted(relation_counts.items(), key=lambda x: x[1])

    result = []
    remaining_samples = num_samples

    # First pass: take all samples from relations with count less than or equal to avg_samples
    for relation, count in sorted_relations:
        if count <= remaining_samples / len(relation_counts):
            result.extend(
                [item for item in data if item["metadata"]["relation"] == relation]
            )
            remaining_samples -= count
            relation_counts.pop(relation)
        else:
            break

    # Second pass: distribute remaining samples among remaining relations
    while remaining_samples > 0 and relation_counts:
        samples_per_relation = max(1, remaining_samples // len(relation_counts))
        for relation in list(
            relation_counts.keys()
        ):  # Use list() to avoid runtime error
            relation_data = [
                item
                for item in data
                if item["metadata"]["relation"] == relation and item not in result
            ]
            samples_to_take = min(
                samples_per_relation, len(relation_data), remaining_samples
            )
            result.extend(random.sample(relation_data, samples_to_take))
            remaining_samples -= samples_to_take
            if relation_counts[relation] <= samples_to_take:
                relation_counts.pop(relation)
            if remaining_samples == 0:
                break

    # Write the sampled data to the output file
    with open(output_file, "w", encoding="utf-8") as outfile:
        for item in result:
            json.dump(item, outfile, ensure_ascii=False)
            outfile.write("\n")

    print(
        f"Sampled {len(result)} items from {input_file} and wrote them to {output_file}"
    )


def process_directory(input_dir, output_dir, num_samples):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    for filename in os.listdir(input_dir):
        if filename.endswith(".jsonl"):
            input_file = os.path.join(input_dir, filename)
            output_file = os.path.join(output_dir, filename)
            stratified_sampling(input_file, output_file, num_samples)


def main():
    parser = argparse.ArgumentParser(
        description="Perform stratified sampling on JSONL files."
    )
    parser.add_argument("input_dir", help="Input directory containing JSONL files")
    parser.add_argument("-o", "--output_dir", help="Output directory for sampled files")
    parser.add_argument(
        "-n",
        "--num_samples",
        type=int,
        default=1000,
        help="Number of samples to take (default: 80)",
    )

    args = parser.parse_args()

    input_dir = args.input_dir
    output_dir = args.output_dir if args.output_dir else input_dir + "_sampled"
    num_samples = args.num_samples

    process_directory(input_dir, output_dir, num_samples)


if __name__ == "__main__":
    main()
