# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

import argparse
from datetime import datetime, timedelta

import requests


def url_exists(url):
    """Check if a URL exists."""
    print(url)
    response = requests.head(url, allow_redirects=True)
    return response.status_code == 200


def download_dumps_bash(
    start_date, num_months, output_file, max_concurrent_operations, s3_path
):
    current_date = datetime.strptime(start_date, "%Y%m%d")
    end_date = current_date + timedelta(
        days=365 * num_months // 12
    )  # Roughly estimate end date
    count_operations = 0

    with open(output_file, "w") as file:
        file.write("#!/bin/bash\n\n")

        while current_date <= end_date:
            found = False
            # Check the 1st and 20th of the month first, then every day
            days_to_check = [1, 20] + [d for d in range(2, 32) if d not in [1, 20]]

            for day in days_to_check:
                try:
                    check_date = current_date.replace(day=day)
                except ValueError:
                    continue  # Skip invalid dates (e.g., February 30th)

                date_str = check_date.strftime("%Y%m%d")
                filename = f"wikidatawiki-{date_str}-pages-articles.xml.bz2"
                url = f"https://archive.org/download/wikidatawiki-{date_str}/{filename}"

                if url_exists(url):
                    # Use run_with_limit for each operation, utilizing aria2c for downloading
                    cmd = f"aria2c -x 16 -s 16 {url} && "
                    cmd += f'aws s3 cp "{filename}" "{s3_path}" && '
                    cmd += f'rm "{filename}"'
                    file.write(f"{cmd} &\n")

                    count_operations += 1
                    if count_operations == max_concurrent_operations:
                        file.write("wait\n")
                        count_operations = 0

                    found = True
                    # Ensure we move to the next month after processing this file
                    current_date = (
                        check_date.replace(day=1) + timedelta(days=32)
                    ).replace(day=1)
                    break  # Exit the loop since we found a file for this month

            if not found:
                # If no dump found in the entire month, ensure we move to the next month
                current_date = (
                    current_date.replace(day=28) + timedelta(days=4)
                ).replace(day=1)

        file.write("wait\n")  # Wait for all background jobs to finish
    print(f"Bash script '{output_file}' has been generated.")


def main():
    parser = argparse.ArgumentParser(description="Download Wikidata dumps using aria2c")
    parser.add_argument(
        "--start-date", required=True, help="Start date in YYYYMMDD format"
    )
    parser.add_argument(
        "--num-months",
        required=True,
        type=int,
        help="Number of months to download after the start date",
    )
    parser.add_argument(
        "--s3-path",
        default="data/raw",
        help="s3 path to upload files after downloading from archive.org",
    )
    parser.add_argument(
        "--concurrent-downloads",
        type=int,
        default=2,
        help="Number of concurrent downloads (default: 2)",
    )
    args = parser.parse_args()

    output_file = "download_dumps_bash_script.sh"
    download_dumps_bash(
        args.start_date,
        int(args.num_months),
        output_file,
        args.concurrent_downloads,
        args.s3_path,
    )


if __name__ == "__main__":
    main()
