# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

import argparse
import json
import os

from transformers import GPTNeoXTokenizerFast


def process_file(input_file, output_file, tokenizer, max_tokens):
    with open(input_file, "r", encoding="utf-8") as infile, open(
        output_file, "w", encoding="utf-8"
    ) as outfile:
        for line in infile:
            try:
                data = json.loads(line)
                context = data.get("context", "")

                # Check if context is a non-empty string
                if not isinstance(context, str):
                    continue  # Skip this line if context is not a string

                if not context.strip():
                    continue  # Skip this line if context is an empty string or only whitespace

                # Tokenize and truncate
                tokens = tokenizer.encode(
                    context, truncation=True, max_length=max_tokens
                )
                truncated_text = tokenizer.decode(tokens)

                # Create new data with truncated context
                new_data = {
                    "context": truncated_text,
                    "continuation": data.get("continuation", ""),
                }

                # Write to output file
                json.dump(new_data, outfile, ensure_ascii=False)
                outfile.write("\n")
            except json.JSONDecodeError:
                print(f"Skipping invalid JSON line in {input_file}")
            except Exception as e:
                print(f"Error processing line in {input_file}: {str(e)}")


def main(input_dir, output_dir, max_tokens):
    # Initialize tokenizer
    tokenizer = GPTNeoXTokenizerFast.from_pretrained("EleutherAI/gpt-neox-20b")

    # If output_dir is not provided, create it by adding '_truncated' to input_dir
    if not output_dir:
        output_dir = input_dir + "_truncated"

    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Process each file in the input directory
    for filename in os.listdir(input_dir):
        if filename.endswith(".jsonl"):
            input_file = os.path.join(input_dir, filename)
            output_file = os.path.join(output_dir, filename)
            process_file(input_file, output_file, tokenizer, max_tokens)
            print(f"Processed {filename}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Tokenize and truncate text using GPT-NeoX-20B tokenizer"
    )
    parser.add_argument("input_dir", help="Input directory containing JSONL files")
    parser.add_argument(
        "--output_dir",
        help="Output directory for truncated files (default: input_dir + '_truncated')",
    )
    parser.add_argument(
        "--max_tokens", type=int, default=450, help="Maximum number of tokens"
    )
    args = parser.parse_args()

    main(args.input_dir, args.output_dir, args.max_tokens)
