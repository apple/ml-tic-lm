# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

"""
Module for extracting vote scores from StackExchange XML data using parallel processing.
"""

import argparse
import json
import os
import re
from typing import Dict, List, Tuple

import ray


@ray.remote
def process_chunk(chunk: List[str]) -> Dict[int, int]:
    post_scores = {}

    for line in chunk:
        if line.strip().startswith("<row "):
            id_match = re.search(r'Id="(\d+)"', line)
            score_match = re.search(r'Score="(-?\d+)"', line)

            if id_match and score_match:
                post_id = int(id_match.group(1))
                score = int(score_match.group(1))
                post_scores[post_id] = score

    return post_scores


def process_file(xml_file_path: str, output_file_path: str):
    chunk_size = 10000
    current_chunk = []
    chunk_futures = []

    with open(xml_file_path, "r") as f:
        for line in f:
            if line.strip().startswith("<row "):
                current_chunk.append(line)
                if len(current_chunk) >= chunk_size:
                    chunk_futures.append(process_chunk.remote(current_chunk))
                    current_chunk = []

    if current_chunk:
        chunk_futures.append(process_chunk.remote(current_chunk))

    chunk_results = ray.get(chunk_futures)

    combined_scores = {}
    for scores in chunk_results:
        combined_scores.update(scores)

    with open(output_file_path, "w") as f:
        json.dump(combined_scores, f)


def main():
    parser = argparse.ArgumentParser(
        description="Extract post scores from StackExchange XML data."
    )
    parser.add_argument("input_xml", help="Path to the input Posts.xml file")
    parser.add_argument(
        "--output_json", required=True, help="Path to the output JSON file"
    )
    args = parser.parse_args()

    if not os.path.exists(args.input_xml):
        print(f"Error: Input file {args.input_xml} does not exist.")
        return

    print(f"Processing {args.input_xml}")
    print(f"Output will be saved to {args.output_json}")

    ray.init()

    print("Processing file and extracting scores...")
    process_file(args.input_xml, args.output_json)
    print("File processing complete.")

    ray.shutdown()
    print(f"Processing complete. Results saved in {args.output_json}")


if __name__ == "__main__":
    main()
