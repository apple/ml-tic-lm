# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

# Some parts of the code is taken from https://github.com/CHLee0801/TemporalWikiDatasets/blob/main/wikidata_datasets.py

import argparse
import json
import os
import random

import ray
from qwikidata.json_dump import WikidataJsonDump

SUPPORT_MODE = ["unchanged", "changed"]
data_base_path = ""
CHUNK_SIZE = 5000

with open(f"{data_base_path}wikidata_properties.json", "r") as read_dictionary:
    property_dict = json.load(read_dictionary)


def write_completion_marker(filename, indices):
    """Write the set of indices to the completion marker file in JSON format."""
    with open(filename, "w") as file:
        json.dump(indices, file)


def read_completion_marker(filename):
    """Read the set of indices from the completion marker file in JSON format."""
    try:
        if os.path.exists(filename):
            with open(filename, "r") as file:
                return json.load(file)
        else:
            return []
    except:
        return []


def read_jsonl_as_dict(jsonl_file):

    combined_dict = {}
    try:
        with open(jsonl_file, "r") as infile:
            for line in infile:
                data = json.loads(line.strip())
                combined_dict.update(data)
    except:
        return {}

    return combined_dict


def extract_dictionaries(text, target):
    target_length = len(target)
    position = 0
    results = []

    while True:
        # Find the next occurrence of the target string
        start = text.find(target, position)
        if start == -1:
            break

        # Start looking for the opening braces from just before the found position
        stack = ["}"]
        i = start

        # Use a stack to find the matching opening braces
        while i >= 0:
            if text[i] == "}":
                stack.append("}")
            elif text[i] == "{":
                if stack and stack[-1] == "}":
                    stack.pop()
                else:
                    # We've found the matching opening brace for all closing braces
                    break
            i -= 1

        # Find the start of the substring
        extract_start = i

        # Reset position for next search
        position = start + target_length

        # Extract the substring and convert it to a dictionary
        try:
            dict_str = text[extract_start : start + target_length]
            # Clean up the string to make it a valid JSON
            # We assume that the substring ends correctly with "}}"
            end = dict_str.rfind("}") + 1
            dict_str = dict_str[:end]
            # Convert string to dictionary
            dict_data = json.loads(dict_str)
            # Check for 'numeric-id' in the nested dictionary
            if "property" in dict_data and "numeric-id" in dict_data.get(
                "datavalue", {}
            ).get("value", {}):
                results.append(
                    [
                        dict_data["property"],
                        f"Q{dict_data['datavalue']['value']['numeric-id']}",
                    ]
                )
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
            continue

    return results


def construct_generation_args():

    parser = argparse.ArgumentParser()
    parser.add_argument("--old", type=str, default="20211101")
    parser.add_argument("--new", type=str, default="20211201")
    parser.add_argument("--idx", type=int, default=0)
    parser.add_argument("--combine", type=int, default=0)


    arg = parser.parse_args()
    return arg


@ray.remote
def extraction(entity_dicts, month, idx):

    big_list = {}

    for ii, entity_dict in enumerate(entity_dicts):
        small_list = []
        entity_id = entity_dict["title"]
        texts = entity_dict["section_texts"][0]

        small_list = extract_dictionaries(texts, '"wikibase-entityid"}}')

        small_list = small_list[:-1]
        semi_result = []
        for i in small_list:
            if i not in semi_result:
                semi_result.append(i)
        big_list[entity_id] = semi_result

    idx = str(idx)
    output_dir = f"{data_base_path}Wikidata_datasets/{month}/{month}_{idx}.jsonl"


    with open(output_dir, "a") as file:
        # Dump the dictionary as a JSON string followed by a newline
        file.write(json.dumps(big_list) + "\n")


def id(old, new, idx, mode):
    old_address = f"{data_base_path}Wikidata_datasets/{old}/{old}_{idx}.jsonl"
    new_address = f"{data_base_path}Wikidata_datasets/{new}/{new}_{idx}.jsonl"
    output_dir = f"{data_base_path}Wikidata_datasets/{old}_{new}/{mode}/{mode}_id/{mode}_{idx}_id.json"

    if os.path.exists(output_dir):
        return None

    previous_python = read_jsonl_as_dict(old_address)
    present_python = read_jsonl_as_dict(new_address)

    if mode == "unchanged":
        unchanged_relation = []
        for entity in previous_python:
            if entity in present_python:
                small = []
                for first_relation in previous_python[entity]:
                    small.append(first_relation)
                for second_relation in present_python[entity]:
                    if second_relation in small:
                        unchanged_relation.append([entity] + second_relation)

        with open(output_dir, "w") as write_json_file:
            json.dump(unchanged_relation, write_json_file, indent=4)

    else:
        new_relation = []
        for entity in previous_python:
            if entity in present_python:
                small = []
                for first_relation in previous_python[entity]:
                    if first_relation[0] not in small:
                        small.append(first_relation[0])
                for second_relation in present_python[entity]:
                    if second_relation[0] not in small:
                        if [
                            entity,
                            second_relation[0],
                            second_relation[1],
                        ] not in new_relation:
                            new_relation.append(
                                [entity, second_relation[0], second_relation[1]]
                            )

        updated_relation = []
        for entity in previous_python:
            if entity in present_python:
                small = []
                new_rel = []
                for first_relation in previous_python[entity]:
                    if first_relation[0] not in small:
                        small.append(first_relation[0])
                for second_relation in present_python[entity]:
                    if second_relation[0] not in small:
                        new_rel.append(second_relation[0])
                same = []
                for i in previous_python[entity]:
                    for j in present_python[entity]:
                        if i == j:
                            same.append(i)
                new_prev = []
                new_pres = []
                for i in previous_python[entity]:
                    if i not in same:
                        new_prev.append(i)
                for i in present_python[entity]:
                    if i not in same:
                        if i[0] not in new_rel:
                            new_pres.append(i)
                included = []
                for first_relation in new_prev:
                    relation = first_relation[0]
                    object = first_relation[1]
                    if len(object) > 15:
                        continue
                    for second_relation in new_pres:
                        if relation == second_relation[0]:
                            if len(second_relation[1]) > 15:
                                continue
                            if object != second_relation[1]:
                                updated_relation.append(
                                    [entity] + first_relation + [second_relation[1]]
                                )
                                included.append(second_relation)
                for i in new_pres:
                    if i not in included:
                        updated_relation.append([entity] + i)

        changed_relation = []
        changed_dic = {}
        for new in new_relation:
            sentence = new[0] + new[1] + new[2]
            if sentence not in changed_dic:
                changed_dic[sentence] = 1
                changed_relation.append(new)
        for update in updated_relation:
            changed_relation.append(update)

        # Detecting new entities and handling random sampling of their relationships
        for entity in present_python:
            if entity not in previous_python:
                # Get all relationships for the new entity
                all_relationships = list(
                    set([tuple(rel) for rel in present_python[entity]])
                )

                # If there are more than 5 relationships, randomly sample 10
                if len(all_relationships) > 10:
                    sampled_relationships = random.sample(all_relationships, 10)
                else:
                    sampled_relationships = all_relationships

                # Add the sampled relationships to the changed_relation list
                for relation in sampled_relationships:
                    changed_relation.append([entity] + list(relation))

        with open(output_dir, "w") as write_json_file:
            json.dump(changed_relation, write_json_file, indent=4)


def name(old, new, idx, mode, entity_dict_id_to_label):
    id_dir = f"{data_base_path}Wikidata_datasets/{old}_{new}/{mode}/{mode}_id/{mode}_{idx}_id.json"
    item_dir = f"{data_base_path}Wikidata_datasets/{old}_{new}/{mode}/{mode}_item/{mode}_{idx}_item.json"
    if os.path.exists(item_dir):
        return None

    with open(id_dir, "r") as read_json_file_1:
        id_list = json.load(read_json_file_1)

    big_list = []
    new_id = []
    if mode == "changed":
        for i in id_list:
            if len(i) == 3:
                sub = i[0]
                rel = i[1]
                obj = i[2]
                if sub in entity_dict_id_to_label:
                    a1 = entity_dict_id_to_label[sub]
                else:
                    continue

                if obj in entity_dict_id_to_label:
                    a3 = entity_dict_id_to_label[obj]
                else:
                    continue

                if len(a3.split()) > 5:
                    continue
                if rel in property_dict:
                    a2 = property_dict[rel]
                else:
                    continue
                big_list.append([a1, a2, a3])
                new_id.append(i)

            elif len(i) == 4:
                sub = i[0]
                rel = i[1]
                obj = i[2]
                obj2 = i[3]
                if sub in entity_dict_id_to_label:
                    a1 = entity_dict_id_to_label[sub]
                else:
                    continue

                if obj in entity_dict_id_to_label:
                    a3 = entity_dict_id_to_label[obj]
                else:
                    continue

                if len(a3.split()) > 5:
                    continue
                if obj2 in entity_dict_id_to_label:
                    a4 = entity_dict_id_to_label[obj2]
                else:
                    continue

                if len(a4.split()) > 5:
                    continue
                if a3.lower() == a4.lower():
                    continue
                if rel in property_dict:
                    a2 = property_dict[rel]
                else:
                    continue
                big_list.append([a1, a2, a4])
                new_id.append([i[0], i[1], i[3]])

        new_big_list = []
        new_big_id_list = []
        for i in range(len(big_list)):
            if big_list[i] not in new_big_list:
                new_big_list.append(big_list[i])
                new_big_id_list.append(new_id[i])

        with open(item_dir, "w") as write_json_file:
            json.dump(new_big_list, write_json_file, indent=4)

        with open(id_dir, "w") as write_json_file_2:
            json.dump(new_big_id_list, write_json_file_2, indent=4)
    else:
        cnt = 0
        for i in id_list:
            cnt += 1
            sub = i[0]
            rel = i[1]
            obj = i[2]
            if sub in entity_dict_id_to_label:
                a1 = entity_dict_id_to_label[sub]
            else:
                continue
            if obj in entity_dict_id_to_label:
                a3 = entity_dict_id_to_label[obj]

            else:
                continue

            if not a3 or len(a3.split()) > 5:
                continue
            if rel in property_dict:
                a2 = property_dict[rel]
            else:
                continue
            big_list.append([a1, a2, a3])
            new_id.append(i)

        with open(item_dir, "w") as write_json_file:
            json.dump(big_list, write_json_file, indent=4)

        with open(id_dir, "w") as write_json_file_2:
            json.dump(new_id, write_json_file_2, indent=4)


def merge(old, new, mode):

    big_id_list = []
    big_item_list = []
    for i in range(100):
        s = str(i)
        id_dir = f"{data_base_path}Wikidata_datasets/{old}_{new}/{mode}/{mode}_id/{mode}_{s}_id.json"
        item_dir = f"{data_base_path}Wikidata_datasets/{old}_{new}/{mode}/{mode}_item/{mode}_{s}_item.json"
        try:
            with open(id_dir, "r") as read_json_1:
                id_list = json.load(read_json_1)
            with open(item_dir, "r") as read_json_2:
                item_list = json.load(read_json_2)
            if len(id_list) != len(item_list):
                continue
            for k in id_list:
                big_id_list.append(k)
            for j in item_list:
                big_item_list.append(j)
        except:
            continue
    id_fname = (
        f"{data_base_path}Wikidata_datasets/{old}_{new}/{mode}/total_{mode}_id.json"
    )
    item_fname = (
        f"{data_base_path}Wikidata_datasets/{old}_{new}/{mode}/total_{mode}_item.json"
    )
    with open(id_fname, "w") as write_json_file_1:
        json.dump(big_id_list, write_json_file_1, indent=4)
    with open(item_fname, "w") as write_json_file_2:
        json.dump(big_item_list, write_json_file_2, indent=4)


@ray.remote
def process_data(old, new, idx, entity_dict_id_to_label):
    for mode in ["changed", "unchanged"]:
        id(
            old, new, idx, mode
        )  # Filter Unchanged, Updated or New factual instances by id
        name(
            old, new, idx, mode, entity_dict_id_to_label
        )  # Mapping id to string item by using 'WikiMapper'


def main():
    arg = construct_generation_args()

    old = arg.old  # old : year + month + date, e.g. 20210801
    new = arg.new  # new : year + month + date, e.g. 20210901
    path = f"Wikidata_datasets/"

    os.makedirs(path + old, exist_ok=True)

    os.makedirs(path + new, exist_ok=True)

    os.makedirs(path + old + "_" + new, exist_ok=True)
    os.makedirs(path + old + "_" + new + "/changed", exist_ok=True)
    os.makedirs(path + old + "_" + new + "/changed/changed_id", exist_ok=True)
    os.makedirs(path + old + "_" + new + "/changed/changed_item", exist_ok=True)
    os.makedirs(path + old + "_" + new + "/unchanged", exist_ok=True)
    os.makedirs(path + old + "_" + new + "/unchanged/unchanged_id", exist_ok=True)
    os.makedirs(path + old + "_" + new + "/unchanged/unchanged_item", exist_ok=True)

    ray.init()  # Initialize Ray

    # Initialize Wikidata JSON dumps
    old_dump = WikidataJsonDump(
        f"{data_base_path}Wikidata_datasets/wikidata-{old}.json.gz"
    )
    new_dump = WikidataJsonDump(
        f"{data_base_path}Wikidata_datasets/wikidata-{new}.json.gz"
    )

    # Check if extraction has already been completed
    old_done_marker = f"{data_base_path}Wikidata_datasets/{old}/extraction_done.json"
    new_done_marker = f"{data_base_path}Wikidata_datasets/{new}/extraction_done.json"

    set_idx = set()
    if os.path.exists(old_done_marker):
        old_dump = []
        set_idx.update(set(read_completion_marker(old_done_marker)))
    if os.path.exists(new_done_marker):
        new_dump = []
        set_idx.update(set(read_completion_marker(new_done_marker)))

    tasks = []
    old_entity_dicts = []
    new_entity_dicts = []

    old_iter = iter(old_dump)
    new_iter = iter(new_dump)
    old_entity = next(old_iter, None)
    new_entity = next(new_iter, None)

    counter = 0

    while old_entity or new_entity:
        if old_entity:
            old_id = int(old_entity["title"][1:])
            old_idx = old_id // CHUNK_SIZE
        if new_entity:
            new_id = int(new_entity["title"][1:])
            new_idx = new_id // CHUNK_SIZE

        # Collect entities for the current minimum index
        while old_entity and int(old_entity["title"][1:]) // CHUNK_SIZE == old_idx:
            old_entity_dicts.append(old_entity)
            old_entity = next(old_iter, None)

        while new_entity and int(new_entity["title"][1:]) // CHUNK_SIZE == new_idx:
            new_entity_dicts.append(new_entity)
            new_entity = next(new_iter, None)

        # Process collected chunks
        if old_entity_dicts:
            set_idx.add(old_idx)
            tasks.append(extraction.remote(old_entity_dicts, old, old_idx))
            old_entity_dicts = []

        # Process collected chunks
        if new_entity_dicts:
            set_idx.add(new_idx)
            tasks.append(extraction.remote(new_entity_dicts, new, new_idx))
            new_entity_dicts = []
        counter += 1
        if counter % 100 == 0:
            # Periodically check and process tasks
            # process_and_clear_tasks()
            ray.get(tasks)
            tasks = []

    # Ensure all remaining tasks are completed
    if tasks:
        final_results = ray.get(tasks)

    write_completion_marker(old_done_marker, list(set_idx))
    write_completion_marker(new_done_marker, list(set_idx))

    # Read dictionary from the JSON file
    with open("wikidata_id_2_label_all/all_id_to_label.json", "r") as file:
        entity_dict_id_to_label = json.load(file)

    tasks = []
    for cnt, index in enumerate(set_idx):
        tasks.append(process_data.remote(old, new, index, entity_dict_id_to_label))
        print(cnt)
        if cnt % 20 == 19:
            # process_and_clear_tasks()
            ray.get(tasks)
            tasks = []

    if tasks:
        final_results = ray.get(tasks)
    ray.shutdown()


if __name__ == "__main__":
    main()
