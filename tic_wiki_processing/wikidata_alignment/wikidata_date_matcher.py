# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

import json
import re
from datetime import datetime

import boto3
import matplotlib.pyplot as plt
import numpy as np


def list_files(bucket, prefix, pattern):
    """List all files in the given S3 bucket and prefix."""
    s3 = boto3.client("s3")
    response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    dates = []
    for item in response.get("Contents", []):
        match = pattern.search(item["Key"])
        if match:
            date = datetime.strptime(match.group(1), "%Y%m%d")
            dates.append(date)
    dates.sort()
    return dates


def calculate_intervals(dates):
    """Calculate intervals between consecutive dates."""
    intervals = []
    for i in range(len(dates) - 1):
        intervals.append((dates[i], dates[i + 1]))
    return intervals


def find_overlapping_interval(wiki_interval, wp_intervals):
    """Find the Wikipedia interval with the maximum overlap with the given Wikidata interval."""
    max_overlap = 0
    best_match = None
    wd_start, wd_end = wiki_interval
    wp_coverage_percent = 0
    for wp_start, wp_end in wp_intervals:
        if wp_start < wd_end and wp_end > wd_start:
            overlap = (min(wd_end, wp_end) - max(wd_start, wp_start)).days
            if overlap > max_overlap:
                max_overlap = overlap
                best_match = (wp_start, wp_end)
                wp_interval_length = (wp_end - wp_start).days
                wp_coverage_percent = (
                    (overlap / wp_interval_length) * 100
                    if wp_interval_length > 0
                    else 0
                )
    wd_interval_length = (wd_end - wd_start).days
    wd_coverage_percent = (
        (max_overlap / wd_interval_length) * 100 if wd_interval_length > 0 else 0
    )
    return wd_coverage_percent, wp_coverage_percent, best_match


import argparse


def parse_s3_path(s3_path):
    """Extract bucket and prefix from S3 path."""
    parts = s3_path.replace("s3://", "").split("/", 1)
    return parts[0], parts[1] if len(parts) > 1 else ""


def parse_args():
    parser = argparse.ArgumentParser(
        description="Configure Wikidata and Wikipedia data locations"
    )

    parser.add_argument(
        "--wikidata-path",
        type=str,
        required=True,
        help="Full S3 path for Wikidata files (e.g., s3://bucket-name/path/to/wikidata/)",
    )
    parser.add_argument(
        "--wikipedia-path",
        type=str,
        required=True,
        help="Full S3 path for Wikipedia files (e.g., s3://bucket-name/path/to/wikipedia/)",
    )

    args = parser.parse_args()

    # Parse paths and return bucket/prefix pairs directly
    wikidata_bucket, wikidata_prefix = parse_s3_path(args.wikidata_path)
    wikipedia_bucket, wikipedia_prefix = parse_s3_path(args.wikipedia_path)

    return wikidata_bucket, wikidata_prefix, wikipedia_bucket, wikipedia_prefix


if __name__ == "__main__":
    # Define buckets, prefixes, and patterns
    wikidata_bucket, wikidata_prefix, wikipedia_bucket, wikipedia_prefix = parse_args()
    wikidata_pattern = re.compile(
        r"wikidatawiki-(\d{8})-pages-articles-multistream.xml.bz2$"
    )
    wikipedia_pattern = re.compile(r"(\d{8}).tar.zstd")

    # Extract dates and calculate intervals
    wikidata_dates = list_files(wikidata_bucket, wikidata_prefix, wikidata_pattern)
    wikipedia_dates = list_files(wikipedia_bucket, wikipedia_prefix, wikipedia_pattern)
    wikidata_intervals = calculate_intervals(wikidata_dates)
    wikipedia_intervals = calculate_intervals(wikipedia_dates)

    # Find overlapping intervals and calculate coverage
    results = [
        find_overlapping_interval(interval, wikipedia_intervals)
        for interval in wikidata_intervals
    ]
    wd_coverage, wp_coverage, matches = zip(*results)

    # Writing results to JSON
    interval_matches = {
        f"{wd[0].strftime('%Y%m%d')}-{wd[1].strftime('%Y%m%d')}": (
            f"{wp[0].strftime('%Y%m%d')}-{wp[1].strftime('%Y%m%d')}" if wp else None
        )
        for wd, wp in zip(wikidata_intervals, matches)
    }
    with open("wikidata/matching_intervals.json", "w") as f:
        json.dump(interval_matches, f, indent=4)

    # Plotting scatter and histograms
    plt.figure(figsize=(12, 6))
    plt.plot(
        wikidata_dates, [2] * len(wikidata_dates), "ro", label="Wikidata", markersize=5
    )
    plt.plot(
        wikipedia_dates,
        [1] * len(wikipedia_dates),
        "bo",
        label="Wikipedia",
        markersize=5,
    )
    plt.legend()
    plt.title("Scatter Plot of Wikidata and Wikipedia Dates")
    plt.xlabel("Date")
    plt.yticks([1, 2], ["Wikipedia", "Wikidata"])
    plt.savefig("wikidata/Wikidata_Wikipedia_Date_Scatter.png")
    plt.show()

    # Histograms for coverage
    plt.figure(figsize=(12, 6))
    plt.hist(wd_coverage, bins=20, color="blue", alpha=0.7, label="Wikidata Coverage")
    plt.hist(wp_coverage, bins=20, color="red", alpha=0.7, label="Wikipedia Coverage")
    plt.title("Histogram of Percentage Coverage of Wikidata and Wikipedia Intervals")
    plt.xlabel("Percentage Coverage")
    plt.ylabel("Frequency")
    plt.legend()
    plt.grid(True)
    plt.savefig("wikidata/Wikidata_Wikipedia_Overlap_Coverage_Comparison.png")
    plt.show()
