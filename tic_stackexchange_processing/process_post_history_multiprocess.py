# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#
"""
Parallel XML Processor for Post History

This module processes a large XML file containing post history data and converts it into
individual JSON files for each unique post. It uses multiprocessing for parallel execution
to improve performance on large datasets.

Input:
    - XML file path: Path to the PostHistory.xml file
    - Output directory: Directory to store the resulting JSON files
    - Batch size: Number of XML elements to process in each batch (default: 10000)
    - Number of processes: Number of parallel processes to use (default: CPU core count)

Output:
    - Multiple JSON files: One file per unique post ID, containing the post's history
      stored in the output directory

Usage:
    python process_post_history_multiprocess.py --input_file <xml_file> --output_dir <output_dir> [--batch_size <size>] [--num_processes <num>]
"""

import argparse
import errno
import fcntl
import json
import logging
import multiprocessing
import os
import random
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from functools import partial

from tqdm import tqdm

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def default_post_data():
    return {
        "title": {"initial": {"text": None, "creation_date": None}, "changes": {}},
        "body": {"initial": {"text": None, "creation_date": None}, "changes": {}},
    }


def process_element(elem):
    try:
        post_id = elem.get("PostId")
        if post_id is None:
            return None

        post_history_type_id = int(elem.get("PostHistoryTypeId", "0"))
        creation_date = elem.get("CreationDate")
        text = elem.get("Text")

        if not all([post_id, post_history_type_id, creation_date, text]):
            return None

        post_data = default_post_data()

        if post_history_type_id == 1:  # Initial Title
            post_data["title"]["initial"]["text"] = text
            post_data["title"]["initial"]["creation_date"] = creation_date
        elif post_history_type_id == 2:  # Initial Body
            post_data["body"]["initial"]["text"] = text
            post_data["body"]["initial"]["creation_date"] = creation_date
        elif post_history_type_id in [4, 7]:  # Title changes
            post_data["title"]["changes"][creation_date] = text
        elif post_history_type_id in [5, 8]:  # Body changes
            post_data["body"]["changes"][creation_date] = text

        return post_id, post_data

    except (AttributeError, ValueError) as e:
        logging.warning(f"Error processing element: {e}")
        return None


def get_subfolder(output_dir, post_id):
    # Convert post_id to integer and determine subfolder
    post_id_int = int(post_id)
    subfolder_num = post_id_int // 300
    subfolder_path = os.path.join(output_dir, f"subfolder_{subfolder_num}")

    # Create subfolder if it doesn't exist
    os.makedirs(subfolder_path, exist_ok=True)

    return subfolder_path


def update_json_file(output_dir, post_id, data):
    subfolder_path = get_subfolder(output_dir, post_id)
    file_path = os.path.join(subfolder_path, f"{post_id}.json")

    while True:
        try:
            with open(file_path, "r+" if os.path.exists(file_path) else "w+") as f:
                fcntl.flock(f, fcntl.LOCK_EX)  # Acquire an exclusive lock
                try:
                    if os.path.getsize(file_path) > 0:
                        f.seek(0)
                        try:
                            existing_data = json.load(f)
                        except json.JSONDecodeError:
                            logging.warning(
                                f"JSON decode error for post {post_id}. Recreating file."
                            )
                            existing_data = default_post_data()
                    else:
                        existing_data = default_post_data()

                    for field in ["title", "body"]:
                        # Add initial value if it doesn't exist
                        if (
                            existing_data[field]["initial"]["text"] is None
                            and data[field]["initial"]["text"] is not None
                        ):
                            existing_data[field]["initial"] = data[field]["initial"]
                        # Add new changes without overwriting existing ones
                        existing_data[field]["changes"].update(data[field]["changes"])

                    f.seek(0)
                    f.truncate()
                    json.dump(existing_data, f, indent=2)
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)  # Release the lock
            return  # Successfully updated, exit the function
        except OSError as e:
            if e.errno == errno.ENOSPC:
                logging.warning(
                    f"No space left on device for post {post_id}. Retrying..."
                )
                time.sleep(1)  # Wait a bit before retrying
            else:
                logging.error(f"OSError for post {post_id}: {e}")
                raise
        except Exception as e:
            sleep_time = random.uniform(0.1, 0.5)
            time.sleep(sleep_time)
            logging.warning(
                f"Error updating JSON file for post {post_id}: {e}. Retrying..."
            )


def process_batch_parallel(batch, output_dir):
    for elem in batch:
        result = process_element(elem)
        if result:
            post_id, post_data = result
            update_json_file(output_dir, post_id, post_data)
        elem.clear()  # Clear element to free up memory


def count_rows(file_path):
    context = ET.iterparse(file_path, events=("end",))
    return sum(1 for event, elem in context if elem.tag == "row")


def process_xml_file(file_path, output_dir, batch_size=10000, num_processes=None):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    total_rows = count_rows(file_path)
    logging.info(f"Total rows to process: {total_rows}")

    context = ET.iterparse(file_path, events=("end",))

    if num_processes is None:
        num_processes = multiprocessing.cpu_count()

    pool = multiprocessing.Pool(processes=num_processes)
    process_batch_partial = partial(process_batch_parallel, output_dir=output_dir)

    batch = []
    with tqdm(total=total_rows, desc="Processing rows", unit="row") as pbar:
        for event, elem in context:
            if elem.tag == "row":
                batch.append(elem)
                pbar.update(1)

            if len(batch) >= batch_size:
                pool.apply_async(process_batch_partial, args=(batch,))
                batch = []

        # Process any remaining data
        if batch:
            pool.apply_async(process_batch_partial, args=(batch,))

    pool.close()
    pool.join()

    logging.info(f"Processing complete.")


def generate_output_dirname(input_path):

    base_name = os.path.basename(input_path)
    name_without_extension = os.path.splitext(base_name)[0]
    return f"{name_without_extension}_processed"


def main():
    parser = argparse.ArgumentParser(
        description="Process PostHistory.xml and create JSON files for each unique PostId."
    )
    parser.add_argument(
        "--input_file", required=True, help="Path to the input PostHistory.xml file"
    )
    parser.add_argument(
        "--output_dir",
        help="Directory to store the output JSON files (default: auto-generated)",
    )
    parser.add_argument(
        "--batch_size",
        type=int,
        default=10000,
        help="Batch size for processing (default: 10000)",
    )
    parser.add_argument(
        "--num_processes",
        type=int,
        default=None,
        help="Number of processes to use (default: number of CPU cores)",
    )

    args = parser.parse_args()

    if args.output_dir is None:
        args.output_dir = generate_output_dirname(args.input_file)

    logging.info(f"Processing file: {args.input_file}")
    logging.info(f"Output directory: {args.output_dir}")
    logging.info(f"Batch size: {args.batch_size}")
    logging.info(f"Number of processes: {args.num_processes or 'Auto'}")

    start_time = time.time()
    process_xml_file(
        args.input_file, args.output_dir, args.batch_size, args.num_processes
    )
    end_time = time.time()

    logging.info(f"Total processing time: {end_time - start_time:.2f} seconds")


if __name__ == "__main__":
    main()
