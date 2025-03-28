# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#


"""
StackExchange Data Processor

This module processes large StackExchange data dumps, creating monthly snapshots of questions and their accepted answers.

Input:
- A large JSONL file with each line containing: {"question_id": int, "accepted_answer_id": int, "answers": [int, ...]}
- A directory of JSON files named [post_id].json, each containing post history with structure:
  {"title": {"initial": {"text": str, "creation_date": str}, "changes": {date: str, ...}},
   "body": {"initial": {"text": str, "creation_date": str}, "changes": {date: str, ...}}}

Output:
- Directory structure: output/[category]/YYYY-MM.jsonl
  where [category] is one of: accepted_answer_appeared, question_or_answer_updated
- Each JSONL file contains lines with: {"question_id": int, "title": str, "body": str, "answers": {id: str, ...}, "accepted_answer_id": int}

Key Features:
1. Processes only questions with accepted answers.
2. Creates snapshots in two categories:
   - Accepted Answer Appeared: When the accepted answer is first provided.
   - Question or Answer Updated: Any updates to the question, accepted answer, or relevant answers after the accepted answer appears.
3. Tracks updates to the question, accepted answer, and relevant answers (answers created before or at the same time as the accepted answer).
4. Ignores updates to answers created after the accepted answer.
"""

import argparse
import fcntl
import glob
import json
import multiprocessing as mp
import os
import time
from collections import defaultdict
from datetime import datetime
from functools import partial

SUBFOLDER = True


def parse_date(date_string):
    if date_string is None:
        return None

    date_formats = [
        "%Y-%m-%dT%H:%M:%S.%f",  # ISO format with microseconds
        "%Y-%m-%dT%H:%M:%S",  # ISO format without microseconds
        "%Y-%m-%d %H:%M:%S",  # Standard format
        "%Y-%m-%d",  # Just date
    ]

    for date_format in date_formats:
        try:
            return datetime.strptime(date_string, date_format)
        except ValueError:
            continue

    print(f"Unable to parse date: {date_string}")
    return None


def read_jsonl_file(file_path, chunk_size=1):
    with open(file_path, "r") as file:
        lines = []
        for line in file:
            lines.append(line.strip())
            if len(lines) == chunk_size:
                yield lines
                lines = []
        if lines:
            yield lines


def load_post_history(post_history_path, post_id):
    if not SUBFOLDER:
        file_path = os.path.join(post_history_path, f"{post_id}.json")
    else:
        post_id_int = int(post_id)
        subfolder_num = post_id_int // 300

        file_path = os.path.join(
            post_history_path, f"subfolder_{subfolder_num}/{post_id}.json"
        )
    try:
        with open(file_path, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        print(f"File not found for post ID {post_id}")
        return {}
    except json.JSONDecodeError:
        print(f"Invalid JSON in file for post ID {post_id}")
        return {}


def get_content_at_timestamp(content_history, timestamp):
    try:
        if not content_history or "initial" not in content_history:
            return None

        current_content = content_history["initial"].get("text")
        creation_date = parse_date(content_history["initial"].get("creation_date"))

        if creation_date is None or timestamp is None:
            return current_content

        if creation_date > timestamp:
            return None

        for change_date, new_content in content_history.get("changes", {}).items():
            parsed_change_date = parse_date(change_date)
            if parsed_change_date and parsed_change_date <= timestamp:
                current_content = new_content
            else:
                break

        return current_content
    except Exception as e:
        print(f"Error in get_content_at_timestamp: {e}")
        print(f"Content history: {content_history}")
        return None


def create_snapshot(post_history, timestamp):
    snapshot = {
        "title": get_content_at_timestamp(post_history.get("title", {}), timestamp),
        "body": get_content_at_timestamp(post_history.get("body", {}), timestamp),
    }
    return snapshot


def collect_all_dates(question_history, answer_histories, accepted_answer_id):
    all_dates = set()
    relevant_answer_ids = set()

    try:
        # First pass: Identify the creation date of the accepted answer
        accepted_answer_date = parse_date(
            answer_histories[accepted_answer_id]
            .get("body", {})
            .get("initial", {})
            .get("creation_date", None)
        )

        if not accepted_answer_date:

            return sorted(all_dates), relevant_answer_ids, accepted_answer_id
        all_dates.add(accepted_answer_date)

        # Determine which answers were created before or at the same time as the accepted answer
        for answer_id, answer_history in answer_histories.items():
            if "body" in answer_history:
                answer_creation_date = parse_date(
                    answer_history.get("body", {})
                    .get("initial", {})
                    .get("creation_date", None)
                )
                if (
                    answer_creation_date
                    and answer_creation_date <= accepted_answer_date
                ):
                    relevant_answer_ids.add(answer_id)

        # Second pass: Collect all relevant dates after the accepted answer appears
        for field in ["title", "body"]:
            if field in question_history:
                for date_str in question_history[field].get("changes", {}).keys():
                    date = parse_date(date_str)
                    if date and date > accepted_answer_date:
                        all_dates.add(date)

        for answer_id in relevant_answer_ids:
            answer_history = answer_histories[answer_id]
            if "body" in answer_history and "changes" in answer_history["body"]:
                for date_str in answer_history["body"]["changes"].keys():
                    date = parse_date(date_str)
                    if date and date > accepted_answer_date:
                        all_dates.add(date)

    except Exception as e:
        print(f"Error in collect_all_dates: {e}")
        print(f"Question history: {question_history}")
        print(f"Answer histories: {answer_histories}")

    return sorted(all_dates), relevant_answer_ids, accepted_answer_id


def save_monthly_snapshots(output_base_path, monthly_snapshots):
    for month, data in monthly_snapshots.items():
        category = data["category"]
        snapshot = data["snapshot"]

        category_path = os.path.join(output_base_path, category)
        os.makedirs(category_path, exist_ok=True)

        file_path = os.path.join(category_path, f"{month}.jsonl")
        lock_path = f"{file_path}.lock"

        while True:
            try:
                with open(lock_path, "w") as lock_file:
                    fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    with open(file_path, "a") as file:
                        json.dump(snapshot, file)
                        file.write("\n")
                    fcntl.flock(lock_file, fcntl.LOCK_UN)
                break
            except IOError:
                # If the file is locked, wait a bit and try again
                time.sleep(0.1)

        # Remove the lock file
        os.remove(lock_path)


def create_monthly_snapshot(
    question_id,
    question_history,
    answer_histories,
    timestamp,
    accepted_answer_id,
    relevant_answer_ids,
):
    question_snapshot = create_snapshot(question_history, timestamp)

    snapshot = {
        "question_id": question_id,
        "title": question_snapshot["title"],
        "body": question_snapshot["body"],
        "answers": {},
        "accepted_answer_id": accepted_answer_id,
    }

    for answer_id in relevant_answer_ids:
        answer_snapshot = create_snapshot(answer_histories[answer_id], timestamp)
        if answer_snapshot["body"] is not None:
            snapshot["answers"][answer_id] = answer_snapshot["body"]

    return snapshot


def get_latest_date_of_month(dates):
    monthly_latest = {}
    for date in dates:
        month_key = date.strftime("%Y-%m")
        if month_key not in monthly_latest or date > monthly_latest[month_key]:
            monthly_latest[month_key] = date
    return sorted(monthly_latest.values())


def process_question(
    question_id, question_history, answer_histories, accepted_answer_id
):
    if accepted_answer_id is None:
        return {}  # Skip questions without an accepted answer

    monthly_snapshots = {}

    all_dates, relevant_answer_ids, accepted_answer_id = collect_all_dates(
        question_history, answer_histories, accepted_answer_id
    )
    latest_monthly_dates = get_latest_date_of_month(all_dates)

    if not relevant_answer_ids:
        return {}

    accepted_answer_date = parse_date(
        answer_histories[accepted_answer_id]["body"]["initial"]["creation_date"]
    )
    accepted_answer_month = accepted_answer_date.strftime("%Y-%m")

    for date in latest_monthly_dates:
        month_key = date.strftime("%Y-%m")

        if month_key == accepted_answer_month:
            category = "accepted_answer_appeared"
        elif date > accepted_answer_date:
            category = "question_or_answer_updated"
        else:
            continue  # Skip snapshots before the accepted answer appeared

        snapshot = create_monthly_snapshot(
            question_id,
            question_history,
            answer_histories,
            date,
            accepted_answer_id,
            relevant_answer_ids,
        )

        monthly_snapshots[month_key] = {"category": category, "snapshot": snapshot}

    return monthly_snapshots


def process_chunk(chunk, post_history_path, output_base_path):
    results = []
    for line in chunk:
        try:
            question_data = json.loads(line)
            question_id = question_data["question_id"]
            answer_ids = question_data["answers"]
            accepted_answer_id = question_data.get("accepted_answer_id")
            if accepted_answer_id is None:
                continue  # Skip questions without an accepted answer
            question_history = load_post_history(post_history_path, question_id)
            answer_histories = {
                id: load_post_history(post_history_path, id) for id in answer_ids
            }

            monthly_snapshots = process_question(
                question_id, question_history, answer_histories, accepted_answer_id
            )
            results.append((monthly_snapshots, question_id))
        except json.JSONDecodeError:
            print(f"Invalid JSON in line: {line}")
        except Exception as e:
            print(f"Error processing question {question_id}: {str(e)}")

    return results


def save_results(results, output_base_path):
    print(f"save_results received {len(results)} items")

    for i, monthly_snapshots in enumerate(results):
        try:
            if not monthly_snapshots[0]:
                continue
            save_monthly_snapshots(output_base_path, monthly_snapshots[0])
        except Exception as e:
            print(f"Error saving results: {str(e)}")
            print(f"Problematic data: {monthly_snapshots}")


def main(input_folder, post_history_path, output_base_path):
    chunk_size = 1000  # Adjust this based on your available memory
    num_processes = mp.cpu_count()
    pool = mp.Pool(processes=num_processes)

    chunk_processor = partial(
        process_chunk,
        post_history_path=post_history_path,
        output_base_path=output_base_path,
    )

    processed_count = 0

    # Get all JSONL files at depth 1 of the input folder
    jsonl_files = glob.glob(os.path.join(input_folder, "*.jsonl"))

    for jsonl_file_path in jsonl_files:
        print(f"Processing file: {jsonl_file_path}")

        for i, chunk in enumerate(
            read_jsonl_file(jsonl_file_path, chunk_size=chunk_size)
        ):
            print(f"Processing chunk {i} of file {os.path.basename(jsonl_file_path)}")
            results = pool.apply_async(chunk_processor, (chunk,))

            # Wait for the chunk to be processed and save results
            chunk_results = results.get()
            save_results(chunk_results, output_base_path)

            processed_count += len(chunk_results)

    pool.close()
    pool.join()

    print(f"Total processed questions: {processed_count}")


def generate_output_path(input_path):
    base_dir = os.path.dirname(input_path)
    input_name = os.path.basename(input_path)
    output_name = f"{input_name}_monthly_snapshots_with_accepted"
    return os.path.join(base_dir, output_name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Process StackExchange data dumps and create monthly snapshots."
    )
    parser.add_argument("--input_path", help="Path to the input JSONL file")
    parser.add_argument(
        "--post_history_path",
        help="Path to the directory containing post history JSON files",
    )
    parser.add_argument(
        "--output_path",
        help="Path to the output directory (default: generated based on input path)",
    )

    args = parser.parse_args()

    input_path = args.input_path
    post_history_path = args.post_history_path
    output_path = (
        args.output_path if args.output_path else generate_output_path(input_path)
    )

    print(f"Input path: {input_path}")
    print(f"Post history path: {post_history_path}")
    print(f"Output path: {output_path}")

    main(input_path, post_history_path, output_path)
