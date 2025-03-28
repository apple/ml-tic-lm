# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

"""
Module for filtering and truncating StackExchange data based on token size constraints.
"""

import argparse
import json
import os

from transformers import GPTNeoXTokenizerFast


def truncate_text(text, max_tokens, tokenizer):
    encoded = tokenizer.encode(text, max_length=max_tokens, truncation=True)
    return tokenizer.decode(encoded)


def process_file(
    input_file, output_file, tokenizer, query_max_tokens, total_max_tokens
):
    filtered_count = 0
    total_count = 0
    with open(input_file, "r", encoding="utf-8") as infile, open(
        output_file, "w", encoding="utf-8"
    ) as outfile:
        for line in infile:
            total_count += 1
            try:
                data = json.loads(line)
                query = data.get("query", "")
                choices = data.get("choices", [])

                if not isinstance(query, str) or not query.strip():
                    filtered_count += 1
                    continue  # Skip this line if query is not a non-empty string

                # Calculate query tokens
                query_tokens = len(tokenizer.encode(query))

                # Filter out if query tokens exceed query_max_tokens
                if query_tokens > query_max_tokens:
                    filtered_count += 1
                    continue

                # Process each choice independently
                truncated_choices = []
                remaining_tokens = total_max_tokens - query_tokens
                for choice in choices:
                    truncated_choice = truncate_text(
                        choice, remaining_tokens, tokenizer
                    )
                    truncated_choices.append(truncated_choice)

                # Update data with truncated choices
                data["choices"] = truncated_choices

                # Write to output file
                json.dump(data, outfile, ensure_ascii=False)
                outfile.write("\n")

            except json.JSONDecodeError:
                print(f"Skipping invalid JSON line in {input_file}")
                filtered_count += 1
            except Exception as e:
                print(f"Error processing line in {input_file}: {str(e)}")
                filtered_count += 1

    return filtered_count, total_count


def main(input_dir, output_dir, query_max_tokens, total_max_tokens):
    # Initialize tokenizer
    tokenizer = GPTNeoXTokenizerFast.from_pretrained("EleutherAI/gpt-neox-20b")

    # Walk through the directory structure
    for root, dirs, files in os.walk(input_dir):
        for file in files:
            if file.endswith(".jsonl"):
                # Construct the full path for input and output files
                input_file = os.path.join(root, file)
                relative_path = os.path.relpath(input_file, input_dir)
                output_file = os.path.join(output_dir, relative_path)

                # Create the output directory if it doesn't exist
                os.makedirs(os.path.dirname(output_file), exist_ok=True)

                # Process the file
                filtered, total = process_file(
                    input_file,
                    output_file,
                    tokenizer,
                    query_max_tokens,
                    total_max_tokens,
                )
                print(
                    f"Processed {relative_path}: {filtered} entries filtered out of {total}"
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Filter and truncate StackExchange data based on token size"
    )
    parser.add_argument("input_dir", help="Input directory containing JSONL files")
    parser.add_argument(
        "--output_dir",
        help="Output directory for filtered and truncated files (default: input_dir + '_filtered_truncated')",
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
    args = parser.parse_args()

    # Set default output directory if not provided
    if not args.output_dir:
        args.output_dir = args.input_dir + "_filtered_truncated"

    main(args.input_dir, args.output_dir, args.query_max_tokens, args.total_max_tokens)
