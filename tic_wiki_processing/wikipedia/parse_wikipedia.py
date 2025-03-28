# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

import argparse
import difflib
import os
import re
from tqdm import tqdm

import pandas as pd
import ray
from smart_open import open


@ray.remote
def read_articles(directory):
    """Read articles from a given directory into a dictionary."""
    articles = {}
    for file in os.listdir(directory):
        full_path = os.path.join(directory, file)
        data = pd.read_json(full_path, lines=True)
        for _, row in data.iterrows():
            articles[row["id"]] = (row["url"], row["title"], row["text"])
    return articles


def preprocess_text(lst):
    new_lst = []
    ref_lst = []
    for line in lst:
        if line.strip() != "":
            line_clean = line.replace("\n", "")
            new_lst.append(line_clean)
            line_normalized = re.sub(r"[^\w\s]", "", line_clean)
            line_normalized = line_normalized.lower()
            ref_lst.append(line_normalized)
    return new_lst, ref_lst


def extract_unchanged_content(old_text, new_text):
    old_paragraphs, old_ref = preprocess_text(old_text.strip().split("\n"))
    new_paragraphs, new_ref = preprocess_text(new_text.strip().split("\n"))

    s = difflib.SequenceMatcher(None, old_ref, new_ref)
    unchanged_content = []

    for tag, i1, i2, j1, j2 in s.get_opcodes():
        if tag == "equal":  # Unchanged paragraphs
            unchanged_content.append("\n".join(old_paragraphs[i1:i2]))
        elif tag == "replace":  # Changed paragraphs, check for unchanged sentences
            old_sents, old_sents_ref = preprocess_text(
                " ".join(old_paragraphs[i1:i2]).split(". ")
            )
            new_sents, new_sents_ref = preprocess_text(
                " ".join(new_paragraphs[j1:j2]).split(". ")
            )
            ss = difflib.SequenceMatcher(None, old_sents_ref, new_sents_ref)
            unchanged_sents = []
            for tag, i1, i2, j1, j2 in ss.get_opcodes():
                if tag == "equal":
                    unchanged_sents.extend(old_sents[i1:i2])
            if unchanged_sents:
                unchanged_content.append(". ".join(unchanged_sents))

    return ". ".join(unchanged_content)


@ray.remote
class CSVWriter:
    def __init__(self, filepath):
        self.filepath = filepath
        self.headers_written = False

    def append_to_csv(self, entries):
        if not entries:
            return
        df = pd.DataFrame(entries, columns=["id", "url", "title", "text"])
        # Use smart_open to handle both local and S3 paths
        with open(self.filepath, "a") as f:
            df.to_csv(f, index=False, header=not self.headers_written)
            if not self.headers_written:
                self.headers_written = True


def count_character_changes(old, new):
    s = difflib.SequenceMatcher(None, old, new)
    changes = sum(
        max(i2 - i1, j2 - j1) > 1
        for tag, i1, i2, j1, j2 in s.get_opcodes()
        if tag != "equal"
    )
    return changes


def extract_changed_content(old_text, new_text, tolerance=1):
    old_paragraphs, old_ref = preprocess_text(old_text.strip().split("\n"))
    new_paragraphs, new_ref = preprocess_text(new_text.strip().split("\n"))

    s = difflib.SequenceMatcher(None, old_ref, new_ref)
    changed_content = []

    for tag, i1, i2, j1, j2 in s.get_opcodes():
        if tag == "replace":
            old_sents, old_sents_ref = preprocess_text(
                re.split(r"(?<=\.)\s+", " ".join(old_paragraphs[i1:i2]))
            )
            new_sents, new_sents_ref = preprocess_text(
                re.split(r"(?<=\.)\s+", " ".join(new_paragraphs[j1:j2]))
            )
            ss = difflib.SequenceMatcher(None, old_sents_ref, new_sents_ref)
            for stag, si1, si2, sj1, sj2 in ss.get_opcodes():
                if stag == "replace":

                    changed_content.append(". ".join(new_sents[sj1:sj2]))
                elif stag == "insert":
                    changed_content.append(". ".join(new_sents[sj1:sj2]))
        elif tag == "insert":
            changed_content.append("\n".join(new_paragraphs[j1:j2]))

    return ". ".join(changed_content)


# %%
@ray.remote
def calculate_differences_batch(batch):
    results = []
    for old_article, new_article, key, url, title in batch:
        # diff = get_difference(old_article, new_article)
        diff = extract_changed_content(old_article, new_article)
        if diff != "":
            results.append([key, url, title, diff.replace("\n", "")])
    return results


@ray.remote
def calculate_unchanged_batch(batch):
    results = []
    for old_article, new_article, key, url, title in batch:
        unchanged_content = extract_unchanged_content(old_article, new_article)
        if unchanged_content != "":
            results.append([key, url, title, unchanged_content.replace("\n", " ")])
    return results


def generate_subsets_csv(old_articles, new_articles, output_path):
    # Setup and reading articles logic remains unchanged

    writer = CSVWriter.remote(output_path)

    all_batches = []  # To keep track of all dispatched batch tasks
    current_batch = []
    with tqdm(total=len(new_articles), desc="Processing articles for differences") as pbar:
        for key, (url, title, new_text) in new_articles.items():
            if key in old_articles and new_text != "":
                _, _, old_text = old_articles[key]
                current_batch.append((old_text, new_text, key, url, title))
                if (len(current_batch) >= 300):  # When batch size reaches 300, dispatch for processing
                    all_batches.append(calculate_differences_batch.remote(current_batch))
                    print(len(all_batches))
                    current_batch = []
            
            elif new_text.replace("\n", "") != "":
                # Handle new articles here, append directly to CSV
                new_entry = [key, url, title, new_text.replace("\n", "")]
                ray.get(writer.append_to_csv.remote([new_entry]))
            
            pbar.update(1)

    # Ensure the last batch is processed if it's not empty
    if current_batch:
        all_batches.append(calculate_differences_batch.remote(current_batch))

    # Wait for all batches to be processed and then write results incrementally
    for batch_future in ray.get(all_batches):
        ray.get(writer.append_to_csv.remote(batch_future))


def generate_unchanged_csv(old_articles, new_articles, output_path):
    # Setup and reading articles logic remains unchanged

    writer = CSVWriter.remote(output_path)

    all_batches = []  # To keep track of all dispatched batch tasks
    current_batch = []
    for key, (url, title, new_text) in new_articles.items():
        if key in old_articles and new_text != "":
            _, _, old_text = old_articles[key]
            current_batch.append((old_text, new_text, key, url, title))
            if (
                len(current_batch) >= 300
            ):  # When batch size reaches 300, dispatch for processing
                all_batches.append(calculate_unchanged_batch.remote(current_batch))
                print(len(all_batches))
                current_batch = []

    # Ensure the last batch is processed if it's not empty
    if current_batch:
        all_batches.append(calculate_unchanged_batch.remote(current_batch))

    # Wait for all batches to be processed and then write results incrementally
    for batch_future in ray.get(all_batches):
        ray.get(writer.append_to_csv.remote(batch_future))

    ray.shutdown()


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Generate diffset of two consequtive dumps of wikipeida in CSV format."
    )
    parser.add_argument("--old_month", type=int, help="Old month in YYYYMMDD format")
    parser.add_argument("--new_month", type=int, help="New month in YYYYMMDD format")
    parser.add_argument(
        "--output_dir",
        type=str,
        default="./",
        help="Directory for the output CSV file. Can be a local path or an S3 bucket path (e.g., s3://bucket/path)",
    )

    args = parser.parse_args()

    ray.init()

    old_month = str(args.old_month)
    new_month = str(args.new_month)

    output_diff_filename = f"wiki_diff_{new_month}_{old_month}.csv"
    output_path_diff = os.path.join(args.output_dir, output_diff_filename)

    output_unchanged_filename = f"wiki_unchanged_{new_month}_{old_month}.csv"
    output_path_unchanged = os.path.join(args.output_dir, output_unchanged_filename)

    new_data_dir = f"{new_month}"  # Newer dump
    old_data_dir = f"{old_month}"
    
    new_article_ids = [
        read_articles.remote(os.path.join(new_data_dir, dir_name))
        for dir_name in sorted(os.listdir(new_data_dir))
    ]
    old_article_ids = [
        read_articles.remote(os.path.join(old_data_dir, dir_name))
        for dir_name in sorted(os.listdir(old_data_dir))
    ]

    new_articles = ray.get(new_article_ids)
    old_articles = ray.get(old_article_ids)

    new_articles = {k: v for d in new_articles for k, v in d.items()}
    old_articles = {k: v for d in old_articles for k, v in d.items()}

    generate_subsets_csv(old_articles, new_articles, output_path_diff)
    generate_unchanged_csv(old_articles, new_articles, output_path_unchanged)
