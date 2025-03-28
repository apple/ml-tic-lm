# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

import argparse
import json
import os
import time

import ray
from qwikidata.json_dump import WikidataJsonDump


def get_label_phrase_match(texts, phrase='"en":{"language":"en","value":"'):
    start_idx = 0
    count = 0
    result = None

    while True:
        start_idx = texts.find(phrase, start_idx)
        if start_idx == -1:
            break
        count += 1
        if count > 1:
            return None  # More than one match found, return None

        # Find the end of the value string
        idx = start_idx + len(phrase)
        while idx < len(texts) and texts[idx] != '"':
            idx += 1

        # Store the potential result but do not return yet
        if result is None:  # Store the first match
            result = texts[start_idx + len(phrase) : idx]

        # Move start index forward to continue searching
        start_idx = idx + 1

    return result


def extract_single_en_label(text):

    target = '"labels":{'
    start = text.find(target)
    if start == -1:
        return None  # The target string was not found

    # Start looking for the opening and closing braces
    stack = []
    i = start + len(target) - 1
    dict_start = i + 1

    # Traverse the text until we find the matching closing brace for the opening brace following "labels":{
    while i < len(text):
        if text[i] == "{":
            stack.append("{")
        elif text[i] == "}":
            if stack:
                stack.pop()
                if not stack:  # No unmatched opening braces left in stack
                    break
        i += 1

    # Extract the substring from just after "labels":{ to the matching closing brace
    dict_str = text[dict_start - 1 : i + 1]

    # Convert the substring to a dictionary and extract "en" if it exists
    try:
        labels_dict = json.loads(dict_str)
        if "en" in labels_dict:
            return labels_dict["en"].get("value", None)
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return get_label_phrase_match(dict_str)


def construct_generation_args():

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--path",
        type=str,
        default="Path to latest gensim processed wikidata dump in json.gz format",
    )

    arg = parser.parse_args()

    return arg


@ray.remote
def process_chunk(entity_dicts):
    entity_id_to_wikidata_label = {}
    entity_id_to_wikipedia_title = {}

    try:
        for entity_dict in entity_dicts:
            entity_id = entity_dict["title"]

            texts = entity_dict["section_texts"][0]
            label = extract_single_en_label(texts)
            wikipedia_title = extract_title(texts)
            if label:
                entity_id_to_wikidata_label[entity_id] = label
            if wikipedia_title:
                entity_id_to_wikipedia_title[entity_id] = wikipedia_title

    except Exception as e:
        print(f"Error processing chunk: {e}")
    return entity_id_to_wikidata_label, entity_id_to_wikipedia_title


def get_labels(dump_location):
    suffix = ".json.gz"
    assert dump_location.endswith(suffix)

    file_name = dump_location.split("/")[-1][: -len(suffix)]
    wjd = WikidataJsonDump(dump_location)

    entity_dicts = []
    sec_id = 0
    try:
        for idx, entity in enumerate(wjd):
            if idx % 1e5 == 0:
                sec_id = int(idx // 1e5)
                process_save_chunk(entity_dicts, f"sec_{sec_id}_{file_name}")
                entity_dicts = []
            entity_dicts.append(entity)
        sec_id += 1
        print(len(entity_dicts))
        process_save_chunk(entity_dicts, f"sec_{sec_id}_{file_name}")
    except Exception as e:
        sec_id += 1
        print(len(entity_dicts))
        process_save_chunk(entity_dicts, f"sec_{sec_id}_{file_name}")
        print(f"Error chunking the data: {e}")


def process_save_chunk(entity_dicts, file_name):
    chunk_size = 1000  # Define chunk size based on your data and system capabilities
    chunks = [
        entity_dicts[i : i + chunk_size]
        for i in range(0, len(entity_dicts), chunk_size)
    ]

    # Process each chunk in parallel
    futures = [process_chunk.remote(chunk) for chunk in chunks]
    results = ray.get(futures)
    output_path = "final_labels_proc/"
    os.makedirs(output_path, exist_ok=True)

    # Aggregate results
    combined_labels = {}
    combined_titles = {}
    for labels, titles in results:
        combined_labels.update(labels)
        combined_titles.update(titles)

    # Write the results to .jsonl files
    with open(f"{output_path}{file_name}_labels.jsonl", "w") as labels_file:
        for id, label in combined_labels.items():
            json.dump({id: label}, labels_file)
            labels_file.write("\n")

    with open(f"{output_path}{file_name}_titles.jsonl", "w") as titles_file:
        for id, title in combined_titles.items():
            json.dump({id: title}, titles_file)
            titles_file.write("\n")


def extract_title(data):

    # Step 1: Find the starting index of '"sitelinks":{'
    start_index = data.find('"sitelinks":{')
    if start_index == -1:
        print("Section 'sitelinks' not found")
        return None

    # Step 2: Extract the dictionary-like string using a stack-based approach
    count = 0  # This will act as a stack counter for braces
    i = start_index + len('"sitelinks":{') - 1  # Start from the opening brace
    while i < len(data):
        if data[i] == "{":
            count += 1
        elif data[i] == "}":
            count -= 1
        if count == 0:
            break
        i += 1

    if count != 0:
        print("Mismatched braces")
        return None

    # The dictionary string
    dict_str = data[start_index : i + 1]

    # Step 3: Find the title within the extracted string
    title_marker = '"enwiki":{"site":"enwiki","title":"'
    title_start = dict_str.find(title_marker)
    if title_start == -1:
        print("enwiki title not found")
        return None

    title_start += len(title_marker)
    title_end = dict_str.find('"', title_start)
    if title_end == -1:
        print("No closing quote for title")
        return None

    # Extract and return the title
    title = dict_str[title_start:title_end]
    return title


if __name__ == "__main__":
    arg = construct_generation_args()
    ray.init()  # Initialize Ray
    start_time = time.time()  # Record the start time
    get_labels(arg.path)
    end_time = time.time()  # Record the end time

    elapsed_time = end_time - start_time
    print(f"Processing time: {elapsed_time:.2f} seconds")  # Print the elapsed time
