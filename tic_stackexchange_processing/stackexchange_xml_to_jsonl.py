# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#
"""
StackExchange XML to JSONL Converter

This module processes large StackExchange XML dumps (Posts.xml) and converts them into JSONL format.
It uses iterative XML parsing and Ray for parallel processing to handle large files efficiently.

Input:
  - Large XML file (Posts.xml) from StackExchange data dump

Output:
  - Multiple JSONL files, each containing batches of questions with their associated answer IDs.
  - Output format per line: {"question_id": int, "accepted_answer_id": int or null, "answers": [int, ...]}

Usage: python stackexchange_xml_to_jsonl.py <path_to_Posts.xml> [-o <output_directory>] [-b <batch_size>]
"""

import argparse
import json
import os
import re
from typing import Dict, List, Tuple

import ray


@ray.remote
def process_chunk(chunk: List[str]) -> Tuple[Dict[int, Dict], Dict[int, List[int]]]:
    question_data = {}
    answer_data = {}

    for line in chunk:
        if line.strip().startswith("<row "):
            # Extract attributes using regex
            id_match = re.search(r'Id="(\d+)"', line)
            post_type_match = re.search(r'PostTypeId="(\d+)"', line)
            parent_id_match = re.search(r'ParentId="(\d+)"', line)
            accepted_answer_match = re.search(r'AcceptedAnswerId="(\d+)"', line)

            if id_match and post_type_match:
                post_id = int(id_match.group(1))
                post_type = post_type_match.group(1)

                if post_type == "1":  # Question
                    accepted_answer_id = (
                        int(accepted_answer_match.group(1))
                        if accepted_answer_match
                        else None
                    )
                    question_data[post_id] = {
                        "accepted_answer_id": accepted_answer_id,
                        "position": len(question_data),
                    }
                elif post_type == "2" and parent_id_match:  # Answer
                    parent_id = int(parent_id_match.group(1))
                    if parent_id in answer_data:
                        answer_data[parent_id].append(post_id)
                    else:
                        answer_data[parent_id] = [post_id]

    return question_data, answer_data


def process_file(xml_file_path: str, dst_folder_path: str, batch_size: int = 10000):
    chunk_size = 10000  # Process 1 million lines at a time
    current_chunk = []
    chunk_futures = []
    chunk_results = []
    cnt = 0
    with open(xml_file_path, "r") as f:
        for i, line in enumerate(f):
            if line.strip().startswith("<row "):
                current_chunk.append(line)
                if len(current_chunk) >= chunk_size:
                    chunk_futures.append(process_chunk.remote(current_chunk))
                    current_chunk = []
                if len(chunk_futures) % 100 == 99:
                    chunk_results.extend(ray.get(chunk_futures))
                    chunk_futures = []
                    cnt += 1
                    print(cnt)

    if current_chunk:
        chunk_futures.append(process_chunk.remote(current_chunk))
        print(f"Submitted final chunk {len(chunk_futures)} for processing")

    chunk_results.extend(ray.get(chunk_futures))

    combined_question_data = {}
    combined_answer_data = {}
    for q_data, a_data in chunk_results:
        combined_question_data.update(q_data)
        for parent_id, answers in a_data.items():
            if parent_id in combined_answer_data:
                combined_answer_data[parent_id].extend(answers)
            else:
                combined_answer_data[parent_id] = answers


    current_batch = []
    batch_id = 1

    for question_id, question_info in combined_question_data.items():
        if question_id not in combined_answer_data.keys():
            continue
        qa_dict = {
            "question_id": question_id,
            "accepted_answer_id": question_info["accepted_answer_id"],
            "answers": combined_answer_data.get(question_id, []),
        }
        current_batch.append(qa_dict)

        if len(current_batch) >= batch_size:
            output_file = os.path.join(
                dst_folder_path, f"stackexchange_data_batch_{batch_id}.jsonl"
            )
            with open(output_file, "w") as f:
                for item in current_batch:
                    f.write(json.dumps(item) + "\n")
            print(f"Wrote batch {batch_id}")
            batch_id += 1
            current_batch = []

    if current_batch:
        output_file = os.path.join(
            dst_folder_path, f"stackexchange_data_batch_{batch_id}.jsonl"
        )
        with open(output_file, "w") as f:
            for item in current_batch:
                f.write(json.dumps(item) + "\n")
        print(f"Wrote final batch {batch_id}")


def main():
    parser = argparse.ArgumentParser(
        description="Process StackExchange XML data into JSONL files."
    )
    parser.add_argument("--input_xml", help="Path to the input Posts.xml file")
    parser.add_argument(
        "-o", "--output", help="Path to the output directory (optional)"
    )
    parser.add_argument(
        "-b",
        "--batch_size",
        type=int,
        default=10000,
        help="Batch size for processing (default: 10000)",
    )
    args = parser.parse_args()

    if args.input_xml is None:
        print("Error: No input XML file specified. Use --help for usage information.")
        return

    input_path = args.input_xml

    if not os.path.exists(input_path):
        print(f"Error: Input file {input_path} does not exist.")
        return

    if args.output:
        output_path = args.output
    else:
        input_dir, input_filename = os.path.split(input_path)
        input_name = os.path.splitext(input_filename)[0]
        output_path = os.path.join(input_dir, f"{input_name}_processed_data")

    os.makedirs(output_path, exist_ok=True)

    print(f"Processing {input_path}")
    print(f"Output will be saved to {output_path}")

    ray.init()

    print("Processing file and collecting data...")
    process_file(input_path, output_path, args.batch_size)
    print("File processing complete.")

    ray.shutdown()
    print(f"Processing complete. Results saved in {output_path}")


if __name__ == "__main__":
    main()
