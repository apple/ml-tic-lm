# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

"""
Module for filtering, truncating, and sampling StackExchange data based on token size and vote differences.
"""
import argparse
import json
import os
import random

from transformers import GPTNeoXTokenizerFast


def is_clear_winner(v1, v2, min_difference=4, min_ratio=4, large_gap=20):
    vote_difference = v1 - v2
    if vote_difference > large_gap:
        return True
    vote_ratio = v1 / v2 if v2 > 0 else float("inf")
    return abs(vote_difference) >= min_difference and vote_ratio >= min_ratio


def truncate_text(text, max_tokens, tokenizer):
    encoded = tokenizer.encode(text, max_length=max_tokens, truncation=True)
    return tokenizer.decode(encoded)


def process_file(
    input_file,
    output_file,
    tokenizer,
    query_max_tokens,
    total_max_tokens,
    sample_size,
    min_questions,
    filter_clear_winner,
):
    with open(input_file, "r", encoding="utf-8") as infile:
        lines = infile.readlines()

    total_count = len(lines)
    shuffled_indices = list(range(total_count))
    random.shuffle(shuffled_indices)

    filtered_count = 0
    valid_entries = []

    for index in shuffled_indices:
        line = lines[index]
        try:
            data = json.loads(line)
            query = data.get("query", "")
            choices = data.get("choices", [])
            metadata = data.get("metadata", {})

            if not isinstance(query, str) or not query.strip():
                filtered_count += 1
                continue

            query_tokens = len(tokenizer.encode(query))

            if query_tokens > query_max_tokens:
                filtered_count += 1
                continue

            # Clear winner filtering
            if filter_clear_winner:
                accepted_answer_votes = metadata.get("accepted_answer_votes", 0)
                other_answer_votes = metadata.get("lowest_voted_answer_votes", 0)
                if not is_clear_winner(accepted_answer_votes, other_answer_votes):
                    filtered_count += 1
                    continue

            truncated_choices = []
            remaining_tokens = total_max_tokens - query_tokens
            for choice in choices:
                truncated_choice = truncate_text(choice, remaining_tokens, tokenizer)
                truncated_choices.append(truncated_choice)

            data["choices"] = truncated_choices
            valid_entries.append(json.dumps(data, ensure_ascii=False))

            if len(valid_entries) >= sample_size:
                break

        except json.JSONDecodeError:
            print(f"Skipping invalid JSON line in {input_file}")
            filtered_count += 1
        except Exception as e:
            print(f"Error processing line in {input_file}: {str(e)}")
            filtered_count += 1

    if len(valid_entries) >= min_questions:
        with open(output_file, "w", encoding="utf-8") as outfile:
            for entry in valid_entries:
                outfile.write(entry + "\n")
        print(
            f"Processed {input_file}: {filtered_count} entries filtered, {len(valid_entries)} entries sampled out of {total_count}"
        )
    else:
        print(
            f"Skipping output for {input_file} due to insufficient valid entries ({len(valid_entries)} < {min_questions})"
        )

    return filtered_count, total_count, len(valid_entries)


def main(
    input_dir,
    output_dir,
    query_max_tokens,
    total_max_tokens,
    sample_size,
    min_questions,
    filter_clear_winner,
):
    tokenizer = GPTNeoXTokenizerFast.from_pretrained("EleutherAI/gpt-neox-20b")

    for root, dirs, files in os.walk(input_dir):
        for file in files:
            if file.endswith(".jsonl"):
                input_file = os.path.join(root, file)
                relative_path = os.path.relpath(input_file, input_dir)
                if relative_path.split("/")[0] not in set(
                    ["math", "stackoverflow", "english"]
                ):

                    continue
                output_file = os.path.join(output_dir, relative_path)

                os.makedirs(os.path.dirname(output_file), exist_ok=True)

                process_file(
                    input_file,
                    output_file,
                    tokenizer,
                    query_max_tokens,
                    total_max_tokens,
                    sample_size,
                    min_questions,
                    filter_clear_winner,
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Efficiently filter, truncate, and sample StackExchange data based on token size"
    )
    parser.add_argument("input_dir", help="Input directory containing JSONL files")
    parser.add_argument(
        "--output_dir",
        help="Output directory for filtered, truncated, and sampled files (default: input_dir + '_filtered_truncated_sampled')",
    )
    parser.add_argument(
        "--query_max_tokens",
        type=int,
        default=1300,
        help="Maximum number of tokens for query (for filtering)",
    )
    parser.add_argument(
        "--total_max_tokens",
        type=int,
        default=1900,
        help="Maximum total number of tokens for query and each choice",
    )
    parser.add_argument(
        "--sample_size",
        type=int,
        default=1000,
        help="Number of entries to sample per file",
    )
    parser.add_argument(
        "--min_questions",
        type=int,
        default=5,
        help="Minimum number of valid entries required to write output file",
    )
    parser.add_argument(
        "--filter_clear_winner",
        type=int,
        default=1,
        help="Enable filtering based on clear winner logic",
    )
    args = parser.parse_args()

    if not args.output_dir:
        args.output_dir = args.input_dir + "_filteredvote_truncated_sampled"

    main(
        args.input_dir,
        args.output_dir,
        args.query_max_tokens,
        args.total_max_tokens,
        args.sample_size,
        args.min_questions,
        args.filter_clear_winner,
    )
