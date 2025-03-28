# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

import json
import os
import sys


def read_and_process_jsonl(path):
    wikidata_to_title = {}
    with open(path, "r", encoding="utf-8") as file:
        for line in file:
            data = json.loads(line)
            for wikidata_id, title in data.items():
                if title.endswith("\\"):
                    title = title[:-1]  # Remove the trailing backslash if present
                try:
                    decoded_title = bytes(title, "utf-8").decode(
                        "unicode_escape"
                    )  # Correcting any encoded characters
                except UnicodeDecodeError:
                    decoded_title = title
                    continue  # Use the original title if decoding fails
                decoded_title = decoded_title.replace("\\/", "/")
                wikidata_to_title[wikidata_id] = decoded_title
    return wikidata_to_title


def save_json(data, path):
    with open(path, "w") as file:
        json.dump(data, file, indent=4)


def create_and_save_mappings(base_dir, jsonl_subdir, json_subdir):
    # Process JSONL files to get Wikidata ID to Wikipedia title mappings
    wikidata_to_title = {}
    jsonl_directory = os.path.join(base_dir, jsonl_subdir)
    for file_name in os.listdir(jsonl_directory):
        if file_name.endswith("_wikidata-20240401_titles.jsonl"):
            file_path = os.path.join(jsonl_directory, file_name)
            wikidata_to_title.update(read_and_process_jsonl(file_path))

    # Reverse mapping: Wikipedia title to Wikidata ID
    title_to_wikidata = {v: k for k, v in wikidata_to_title.items()}

    # Read JSON files that map numerical ID to Wikipedia title
    num_id_to_title = {}
    json_directory = os.path.join(base_dir, json_subdir)
    for file_name in os.listdir(json_directory):
        if file_name.startswith("id_to_title_segment_"):
            file_path = os.path.join(json_directory, file_name)
            with open(file_path, "r", encoding="utf-8") as file:
                num_id_to_title.update(json.load(file))

    # Map numerical ID to Wikidata ID using Wikipedia titles as intermediary
    num_id_to_wikidata = {}
    unmatched_ids = []
    for num_id, title in num_id_to_title.items():
        if title in title_to_wikidata:
            num_id_to_wikidata[num_id] = title_to_wikidata[title]
        else:
            unmatched_ids.append(num_id)

    # Save mappings and unmatched IDs
    save_json(title_to_wikidata, os.path.join(base_dir, "wikipedia_to_wikidata.json"))
    save_json(num_id_to_wikidata, os.path.join(base_dir, "num_id_to_wikidata.json"))
    save_json(unmatched_ids, os.path.join(base_dir, "unmatched_ids.json"))


if __name__ == "__main__":

    base_directory = "wikidata/processed_labels"
    jsonl_subdirectory = "wikidata20240401_enwiki_title_and_wikidata_label"
    json_subdirectory = "wikipeida20240401_id_to_title"
    create_and_save_mappings(base_directory, jsonl_subdirectory, json_subdirectory)
