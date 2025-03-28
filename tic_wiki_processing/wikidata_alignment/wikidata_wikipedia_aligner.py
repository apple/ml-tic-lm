# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

import argparse
import gc
import json
import os
import re

import pandas as pd
import ray

cur_dir = "."


def normalize_text(text):
    """Normalize text by removing extra spaces, fixing commas and capitalization."""
    text = text.lower()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def sentence_extraction(text, object, subject=None):
    """Extract sentences containing the object and optionally the subject."""
    sentences_with_object = []
    sentences_with_both = []
    for sentence in text.split(". "):
        normalized_sentence = normalize_text(sentence)
        if object in normalized_sentence:
            sentences_with_object.append(sentence)
            if subject and subject in normalized_sentence:
                sentences_with_both.append(sentence)
    return sentences_with_object, sentences_with_both


def remove_commas(item):
    """Remove commas from the item for processing."""
    return "".join([i for i in item if i != ","])


@ray.remote
def aligning(idx, old, new, mode, id_text_dict, wikidata_to_wikipedia):
    """Process alignment for a specific index and date range."""

    wikidata_ids_path = (
        f"{cur_dir}/Wikidata_datasets/{old}_{new}/{mode}/{mode}_id/{mode}_{idx}_id.json"
    )
    wikidata_items_path = f"{cur_dir}/Wikidata_datasets/{old}_{new}/{mode}/{mode}_item/{mode}_{idx}_item.json"

    with open(wikidata_ids_path, "r") as file:
        wikidata_ids = json.load(file)
    with open(wikidata_items_path, "r") as file:
        wikidata_items = json.load(file)

    assert len(wikidata_ids) == len(wikidata_items)

    processed_data = []
    used_items = set()  # To avoid duplicates
    for index, wikidata_id in enumerate(wikidata_ids):
        wikipedia_id = wikidata_to_wikipedia.get(wikidata_id[0])

        if wikipedia_id and wikipedia_id in id_text_dict:
            text = id_text_dict[wikipedia_id]
            subject = wikidata_items[index][0]
            relation = wikidata_items[index][1]
            object = wikidata_items[index][2]
            object_normalized = normalize_text(object)
            subject_normalized = normalize_text(subject)
            if (
                object_normalized in subject_normalized
                or subject_normalized in object_normalized
                or len(object_normalized.split()) > 5
            ):
                continue

            sentences_object, sentences_both = sentence_extraction(
                text, object_normalized, subject_normalized
            )
            item_tuple = (subject, relation, object)
            if item_tuple not in used_items:
                used_items.add(item_tuple)
                if sentences_object or sentences_both:
                    processed_data.append(
                        {
                            "subject": remove_commas(subject),
                            "relation": remove_commas(relation),
                            "object": remove_commas(object),
                            "sentences_with_object": sentences_object,
                            "sentences_with_both": sentences_both,
                        }
                    )

    output_file = f"{cur_dir}/Wikidata_datasets/{old}_{new}/{mode}/processed/processed_items_{idx}.csv"
    os.makedirs(
        f"{cur_dir}/Wikidata_datasets/{old}_{new}/{mode}/processed/", exist_ok=True
    )
    pd.DataFrame(processed_data).to_csv(output_file, index=False)
    return f"Processing completed for index {idx}."


# Function to process results in batches
def process_in_batches(task_ids, batch_size=10):
    # Collect results in batches
    for i in range(0, len(task_ids), batch_size):
        batch = task_ids[i : i + batch_size]
        results = ray.get(batch)
        # Here you can process your results or yield them
        yield results


def main():
    parser = argparse.ArgumentParser(description="Align text data.")
    parser.add_argument(
        "--mode", type=str, required=True, help="Mode: unchanged or changed"
    )
    parser.add_argument(
        "--old", type=str, required=True, help="Old date in YYYYMMDD format"
    )
    parser.add_argument(
        "--new", type=str, required=True, help="New date in YYYYMMDD format"
    )
    args = parser.parse_args()

    with open("wikidata/matching_intervals.json", "r") as file:
        date_mapping = json.load(file)

    mode, old, new = args.mode, args.old, args.new
    wikidata_range = f"{old}-{new}"
    wikipedia_range = date_mapping[wikidata_range]
    wikipedia_start, wikipedia_end = wikipedia_range.split("-")

    # Find all indices from available data files
    path = (
        f"{cur_dir}/Wikidata_datasets/{args.old}_{args.new}/{args.mode}/{args.mode}_id/"
    )

    indices = [f.split("_")[1] for f in os.listdir(path) if f.endswith("_id.json")]

    mode = args.mode

    if mode == "changed":
        data_subset_path = f"{cur_dir}/Wikipedia_datasets/wiki_diff_{wikipedia_end}_{wikipedia_start}.csv"
    else:
        data_subset_path = f"{cur_dir}/Wikipedia_datasets/wiki_unchanged_{wikipedia_end}_{wikipedia_start}.csv"

    wikidata_to_wikipedia_path = f"wikidata_id_to_wikipedia_id.json"

    # Load data files
    df = pd.read_csv(data_subset_path)
    df["id"] = df["id"].astype(str)
    id_text_dict = pd.Series(df["text"].values, index=df["id"]).to_dict()
    del df
    gc.collect()

    with open(wikidata_to_wikipedia_path, "r") as file:
        wikidata_to_wikipedia = json.load(file)

    # Initialize Ray
    # ray.init(logging_level=logging.INFO)
    ray.init()

    # Process results in batches
    batch_size = 200
    for i in range(0, len(indices), batch_size):
        result_ids = [
            aligning.remote(
                idx, args.old, args.new, args.mode, id_text_dict, wikidata_to_wikipedia
            )
            for idx in indices[i : i + batch_size]
        ]
        ray.get(result_ids)
    ray.shutdown()


if __name__ == "__main__":
    main()
