# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

import argparse
import csv
import glob
import json
import os
import re


def normalize_text(text):
    """Normalize text by removing extra spaces, fixing commas and capitalization."""
    text = text.lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def create_blank_sentence(sentence, object_text):
    """Replace the object in the sentence with a blank, preserving original capitalization."""
    normalized_sentence = normalize_text(sentence)
    normalized_object = normalize_text(object_text)

    pattern = r"\b" + re.escape(normalized_object) + r"\b"
    blanked_sentence_lower = re.sub(
        pattern, "_____", normalized_sentence, flags=re.IGNORECASE
    )

    if blanked_sentence_lower == normalized_sentence:
        blanked_sentence_lower = re.sub(
            re.escape(normalized_object),
            "_____",
            normalized_sentence,
            flags=re.IGNORECASE,
        )

    # Preserve original capitalization
    blanked_sentence = ""
    lower_index = 0
    for char in sentence:
        if lower_index < len(blanked_sentence_lower):
            if char.lower() == blanked_sentence_lower[lower_index]:
                blanked_sentence += char
                lower_index += 1
            else:
                blanked_sentence += blanked_sentence_lower[lower_index]
                lower_index += 1
        else:
            break

    return blanked_sentence


def generate_object_variations(object_text):
    """Generate variations of the object text."""
    variations = [
        object_text,
        object_text.lower(),
        object_text.upper(),
        object_text.capitalize(),
        object_text.title(),
        " ".join(object_text.split()),  # Remove extra spaces
        object_text.strip(),  # Remove leading/trailing spaces
    ]
    return list(set(variations))  # Remove duplicates


def process_csv(input_file, output_file_object, output_file_both, append_mode=False):
    mode = "a" if append_mode else "w"
    with open(input_file, "r", encoding="utf-8") as csvfile, open(
        output_file_object, mode, encoding="utf-8"
    ) as jsonfile_object, open(
        output_file_both, mode, encoding="utf-8"
    ) as jsonfile_both:
        reader = csv.DictReader(csvfile)
        for row in reader:
            subject = row["subject"]
            relation = row["relation"]
            object_text = row["object"]

            # Process sentences with object only
            if row["sentences_with_object"]:
                sentences = eval(row["sentences_with_object"])
                if sentences:
                    sentence = sentences[0]  # Take only the first sentence
                    if sentence.strip():  # Check if sentence is not empty
                        blanked_sentence = create_blank_sentence(sentence, object_text)

                        question_data = {
                            "context": f"Question: Regarding {subject}, fill in the blank: {blanked_sentence}\nAnswer:",
                            "answer": object_text,
                            "aliases": generate_object_variations(object_text),
                            "metadata": {"relation": relation},
                        }

                        json.dump(question_data, jsonfile_object, ensure_ascii=False)
                        jsonfile_object.write("\n")

            # Process sentences with both subject and object
            if row["sentences_with_both"]:
                sentences = eval(row["sentences_with_both"])
                if sentences:
                    sentence = sentences[0]  # Take only the first sentence
                    if sentence.strip():  # Check if sentence is not empty
                        blanked_sentence = create_blank_sentence(sentence, object_text)

                        question_data = {
                            "context": f"Question: Fill in the blank: {blanked_sentence}\nAnswer:",
                            "answer": object_text,
                            "aliases": generate_object_variations(object_text),
                            "metadata": {"relation": relation},
                        }

                        json.dump(question_data, jsonfile_both, ensure_ascii=False)
                        jsonfile_both.write("\n")


def process_directory(input_dir, output_file_object, output_file_both):
    csv_files = glob.glob(os.path.join(input_dir, "*.csv"))
    for i, csv_file in enumerate(csv_files):
        print(f"Processing file {i+1}/{len(csv_files)}: {csv_file}")
        process_csv(csv_file, output_file_object, output_file_both, append_mode=(i > 0))


def main():
    parser = argparse.ArgumentParser(
        description="Process CSV file(s) to create question-answer pairs."
    )
    parser.add_argument(
        "input_path", help="Input CSV file or directory containing CSV files"
    )
    parser.add_argument("--output", help="Base name for output files")

    args = parser.parse_args()

    input_path = args.input_path

    # Create llm_foundry_processed folder if it doesn't exist
    output_dir = os.path.join(os.getcwd(), "llm_foundry_processed")
    os.makedirs(output_dir, exist_ok=True)

    if args.output:
        base_name = args.output
    else:
        base_name = (
            os.path.splitext(os.path.basename(input_path))[0]
            if os.path.isfile(input_path)
            else os.path.basename(input_path.rstrip("/"))
        )

    output_file_object = os.path.join(output_dir, f"{base_name}_object.jsonl")
    output_file_both = os.path.join(output_dir, f"{base_name}_both.jsonl")

    if os.path.isdir(input_path):
        print(f"Processing directory: {input_path}")
        process_directory(input_path, output_file_object, output_file_both)
    else:
        print(f"Processing file: {input_path}")
        process_csv(input_path, output_file_object, output_file_both)

    print(f"Processing complete. Output files:")
    print(f"1. Sentences with object only: {output_file_object}")
    print(f"2. Sentences with both subject and object: {output_file_both}")


if __name__ == "__main__":
    main()
