# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

"""
Module for parsing and extracting question-answer pairs from StackExchange XML dumps.
"""

import argparse
import glob
import json
import math
import os
import re
import urllib
from datetime import datetime
from pathlib import Path

import ftfy
import pandas as pd
from joblib import Parallel, cpu_count, delayed
from pyunpack import Archive
from tqdm import tqdm


def remove_html_tags(text: str, skip_html_tag_parsing: bool = True) -> str:
    """Remove the html tags from the input string.

    The default behavior is to skip html tag parsing, but can be enabled by setting 'skip_html_tag_parsing=False'.
    """

    if skip_html_tag_parsing:
        return text

    if isinstance(text, str):
        # remove html tags
        html_re = re.compile("<.*?>")
        text = urllib.parse.unquote(text)
        text = text.replace("+", " ")
        text = re.sub(html_re, "", str(text))
        # replace multiple spaces with a single space
        text = re.sub(" +", " ", text)
        text = ftfy.fix_text(text)
        return text
    return text


def extract_comments(comments_data_df, post_id):
    """Helper function to extact comments from the data."""
    filtered_comment_rows = comments_data_df.query(f"PostId == {post_id}")
    if not filtered_comment_rows.empty:
        comments = []
        for _, comment_row in filtered_comment_rows.iterrows():
            comments.append(comment_row["Text"])
        return comments
    return None


def parse_data(
    xml_folder_path: str, dst_json_fname: str, extra_info: str, dst_folder_path: str
) -> None:
    """Parses the xml data into json format.

    This function reads two xml files, i.e., Posts and Comments, and constructs question-answer pairs,
    which are then stored in json format in chronological order.

    Args:
        xml_folder_path: Path of the folder containing extracted xml files from 7z compressed file.
        dst_json_fname: Name of the output json file name.
        extra_info: A string containing extra information about the source folder structures.
            For example, if the 7z file name is 'src_data/3dprinting/3dprinting.meta.stackexchange.com', then
            this variable would contain '3dprinting' as extra information.
        dst_folder_path: Destination folder where results should be stored.

    Returns:
        None

    ...note:
    For information about the tags, please see https://meta.stackexchange.com/questions/2677/database-schema-documentation-for-the-public-data-dump-and-sede/2678#2678
    """

    posts_data_df = pd.read_xml(os.path.join(xml_folder_path, "Posts.xml"))
    comments_data_df = pd.read_xml(os.path.join(xml_folder_path, "Comments.xml"))

    for _, row in posts_data_df.iterrows():
        post_id = row["Id"]
        post_type_id = row["PostTypeId"]
        accepted_answer_id = row["AcceptedAnswerId"]
        if post_type_id == 2:
            # skip rows related to answers
            continue

        if not isinstance(row["Body"], str) and math.isnan(row["Body"]):
            # skip rows that does not have body
            continue

        if not isinstance(row["Title"], str):
            # skip rows without title
            continue

        qa_dict = {
            "question": {
                "title": remove_html_tags(row["Title"]),
                "body": remove_html_tags(row["Body"]),
                "creation_date": row["CreationDate"],
                "view_count": row["ViewCount"],
            }
        }

        # Extract the comments related to question
        comments = extract_comments(comments_data_df=comments_data_df, post_id=post_id)
        if comments is not None:
            qa_dict["question"]["comments"] = comments

        # Extract all answers to the question. Note that 'is_accepted' flag is used to indicate if
        # answer is an accepted answer or not.
        answer_rows = posts_data_df.query(f"ParentId == {post_id}")
        if not answer_rows.empty:
            answers = []
            for _, answer_row in answer_rows.iterrows():
                answer_id = answer_row["Id"]
                answer_dict = {
                    "body": remove_html_tags(answer_row["Body"]),
                    "creation_date": answer_row["CreationDate"],
                    "score": answer_row["Score"],
                    "is_accepted": (
                        (answer_id == int(accepted_answer_id))
                        if not math.isnan(accepted_answer_id)
                        else False
                    ),
                }
                if not math.isnan(answer_row["ViewCount"]):
                    answer_dict["view_count"] = answer_row["ViewCount"]

                answer_comments = extract_comments(
                    comments_data_df=comments_data_df, post_id=answer_id
                )
                if answer_comments is not None:
                    answer_dict["comments"] = answer_comments
                answers.append(answer_dict)
            qa_dict["answers"] = answers

        date_time_info = datetime.strptime(row["CreationDate"], "%Y-%m-%dT%H:%M:%S.%f")
        """
        If src_data is organized as
        src_path/
        |- 3dprinting
        |---- 3dprinting.meta.stackexchange.com.7z
        ....

        then parsed data will be organized as 
        parsed_data/
        |- 201601 <--- YYYYMM format for timestamp information
        |---- 3dprinting
        |-------- 3dprinting.meta.stackexchange.com.json
        .....
        |- 200808
        ....
        """
        dst_path_with_timestamp = f"{dst_folder_path}/{date_time_info.year:04d}{date_time_info.month:02d}/{extra_info}"
        Path(dst_path_with_timestamp).mkdir(exist_ok=True, parents=True)

        with open(f"{dst_path_with_timestamp}/{dst_json_fname}", "a") as f:
            f.write(json.dumps(qa_dict) + "\n")


def main_worker(src_7z_fname):
    try:
        # extract 7z file
        xml_folder_path = src_7z_fname.replace(".7z", "")
        Path(xml_folder_path).mkdir(exist_ok=True, parents=True)
        Archive(src_7z_fname).extractall(xml_folder_path)
        path_file_info = (
            src_7z_fname.replace(f"{src_path}/", "")
            .replace(".7z", ".json")
            .split(os.sep)
        )

        src_extra_info = "/".join(path_file_info[:-1])
        parse_data(xml_folder_path, path_file_info[-1], src_extra_info, dst_path)
    except Exception as e:
        print(f"Error: {str(e)} with {src_7z_fname}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--src-path",
        default="src_data",
        type=str,
        help="Local location of the raw stackexchange data. Defaults to 'src_data'.",
    )
    parser.add_argument(
        "--dst-path",
        default="parsed_data",
        type=str,
        help="Local location of the parsed data. Defaults to 'parsed_data'.",
    )
    opts = parser.parse_args()

    # the data in src_path is organized as
    """
    src_path/
       |- 3dprinting
       |---- 3dprinting.meta.stackexchange.com.7z
       |---- 3dprinting.stackexchange.com.7z
       ...
       |- bioacoustics
       ....
    """
    src_path = getattr(opts, "src_path")

    dst_path = getattr(opts, "dst_path")

    # all sub-folders inside src_path
    # Note that there are other 7z files in some folders (e.g., stackoverflow.com-Users.7z) that
    # requires a bit of structure organization, so those are processed independently.
    # If there are any errors, we will skip processing them and instead, print error message along with file name for now (so that it can be debugged later).
    src_7z_fnames = glob.glob(f"{src_path}/*/*.7z")
    # remove the stackoverflow 7z filenames
    src_7z_fnames = [
        f_name
        for f_name in src_7z_fnames
        if f_name.find("stackoverflow/stackoverflow.com-") < 0
    ]
    if len(src_7z_fnames) > 0:
        n_jobs = max(1, cpu_count())

        print("Processing all 7z files except stackoverflow....")
        results = Parallel(n_jobs=n_jobs)(
            delayed(main_worker)(src_7z_fname) for src_7z_fname in tqdm(src_7z_fnames)
        )

        # Process stackoverflow data
        print("Processing stackoverflow....")
        stackoverflow_fnames = [
            f"{src_path}/stackoverflow/stackoverflow.com-Comments.7z",
            f"{src_path}/stackoverflow/stackoverflow.com-Posts.7z",
        ]
        xml_folder_path = f"{src_path}/stackoverflow/stackoverflow.com"
        Path(xml_folder_path).mkdir(exist_ok=True, parents=True)
        for stackoverflow_fname in stackoverflow_fnames:
            Archive(stackoverflow_fname).extractall(xml_folder_path)

        path_file_info = "stackoverflow/stackoverflow.com.json"

        src_extra_info = "stackoverflow"
        parse_data(xml_folder_path, "stackoverflow.com", src_extra_info, dst_path)
        print("Processing done!")
    else:
        print(f"Error: No 7z files exist in {src_path}. Please check.")
