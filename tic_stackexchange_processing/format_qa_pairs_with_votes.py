# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

"""
Module for converting StackExchange question-answer pairs into LLM Foundry format with vote information.
"""

import argparse
import glob
import json
import os
from collections import defaultdict

from tqdm import tqdm


def load_votes(votes_file):
    with open(votes_file, "r") as f:
        return json.load(f)


def convert_stackexchange_to_llm_foundry(input_data, votes):
    title = input_data["title"]
    body = input_data["body"]
    answers = input_data["answers"]
    accepted_answer_id = str(input_data["accepted_answer_id"])

    if accepted_answer_id not in answers:
        return None

    query = f"Question Title: {title}\n\nQuestion Body: {body}"

    accepted_answer = answers[accepted_answer_id]
    accepted_answer_votes = votes.get(accepted_answer_id, 0)

    other_answers = [
        (aid, a) for aid, a in answers.items() if aid != accepted_answer_id
    ]
    if not other_answers:
        return None

    lowest_voted_answer_id, lowest_voted_answer = min(
        other_answers, key=lambda x: votes.get(x[0], 0)
    )
    lowest_voted_answer_votes = votes.get(lowest_voted_answer_id, 0)

    if accepted_answer_votes <= lowest_voted_answer_votes:
        return None

    choices = [accepted_answer, lowest_voted_answer]
    gold = 0  # accepted answer is always the first choice

    question_votes = votes.get(str(input_data["question_id"]), 0)

    metadata = {
        "question_votes": question_votes,
        "accepted_answer_votes": accepted_answer_votes,
        "lowest_voted_answer_votes": lowest_voted_answer_votes,
    }

    return {"query": query, "choices": choices, "gold": gold, "metadata": metadata}


def process_files(input_dir, llm_foundry_dir, votes_file):
    os.makedirs(llm_foundry_dir, exist_ok=True)
    votes = load_votes(votes_file)
    filtered_count = 0
    total_count = 0

    input_files = glob.glob(os.path.join(input_dir, "*.jsonl"))

    for input_file in tqdm(
        input_files, desc=f"Processing {os.path.basename(input_dir)}"
    ):
        filename = os.path.basename(input_file)
        llm_foundry_file = os.path.join(llm_foundry_dir, filename)

        with open(input_file, "r") as infile, open(
            llm_foundry_file, "w"
        ) as llm_outfile:
            for line in infile:
                total_count += 1
                input_data = json.loads(line.strip())
                converted_data = convert_stackexchange_to_llm_foundry(input_data, votes)

                if converted_data:
                    json.dump(converted_data, llm_outfile)
                    llm_outfile.write("\n")
                else:
                    filtered_count += 1

    return filtered_count, total_count


def process_category(input_dir, category, llm_foundry_base_dir, votes_file):
    category_dir = os.path.join(input_dir, category)
    # category_dir = input_dir
    llm_foundry_dir = llm_foundry_base_dir

    filtered_count, total_count = process_files(
        category_dir, llm_foundry_dir, votes_file
    )

    return filtered_count, total_count


def transform_directory_path(input_dir):
    # Get the parent directory
    parent_dir = os.path.dirname(input_dir)

    # Get the name of the input directory (child)
    child_name = os.path.basename(input_dir)

    # Create the new parent directory name
    new_parent_dir = parent_dir + "_llm_foundry_format"

    # Combine the new parent directory with the original child name
    new_path = os.path.join(new_parent_dir, child_name)

    return new_path


def main(input_dir, votes_file):
    llm_foundry_base_dir = transform_directory_path(input_dir)
    os.makedirs(llm_foundry_base_dir, exist_ok=True)

    total_filtered = 0
    total_questions = 0

    for category in ["accepted_answer_appeared"]:
        filtered_count, category_total = process_category(
            input_dir, category, llm_foundry_base_dir, votes_file
        )
        total_filtered += filtered_count
        total_questions += category_total
        print(f"Category {category}:")
        print(f"  Total questions: {category_total}")
        print(f"  Filtered out: {filtered_count}")
        print(f"  Percentage filtered: {(filtered_count / category_total) * 100:.2f}%")
        print()

    print(f"Overall statistics:")
    print(f"  Total questions processed: {total_questions}")
    print(f"  Total filtered out: {total_filtered}")
    print(
        f"  Overall percentage filtered: {(total_filtered / total_questions) * 100:.2f}%"
    )
    print(f"Processing complete. Output files saved in {llm_foundry_base_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Process StackExchange data and generate LLM Foundry format for specified categories."
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Directory containing category subdirectories",
    )
    parser.add_argument(
        "--votes-file", required=True, help="Path to the votes.json file"
    )

    args = parser.parse_args()

    main(args.input_dir, args.votes_file)
