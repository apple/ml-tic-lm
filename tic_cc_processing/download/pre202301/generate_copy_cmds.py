# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
# 

import argparse
import os
import re
import hashlib

# Extract month from DCLM-Pool paths
MONTH_EXTRACTOR = re.compile(r"/CC-MAIN-(\d{6,6})")

# Mapping from a DCLM-Pool jsonl.gz path back to the original CC warc.gz path
def dclm_to_warc_path(dclm_path):
    warc_path = dclm_path.replace("/contrib/datacomp/DCLM-pool/", "/crawl-data/").replace("jsonl.gz", "warc.gz").replace("crawl=","")
    warc_path = re.sub(r"(CC-MAIN.*/)(.*)(/CC-MAIN)", r"\g<1>segments/\g<2>/warc\g<3>", warc_path)
    return warc_path

parser = argparse.ArgumentParser(description='Generate copy commands for TiC-CC processing')
parser.add_argument('--input', type=str, help='Input file with list of files from DCLM-Pool to copy.')
parser.add_argument("--dest-dir", type=str, help='Destination directory for storing TiC-CC')
parser.add_argument('--output', type=str, default="copy_cmds.txt", help='Output file with copy commands')
parser.add_argument('--use-aws-cli', action='store_true', help='Use s5cmd format for copy commands')
parser.add_argument("--verbose", action='store_true')

args = parser.parse_args()

with open(args.input, 'r') as f:
    paths = f.read().splitlines()

cmds = []
for path in paths:
    month = MONTH_EXTRACTOR.search(path).group(1)

    # Basenames are not completely unique so we add same hash as is generated in DCLM's extraction script
    warc_path = dclm_to_warc_path(path)
    short_md5 = hashlib.md5(warc_path.encode()).hexdigest()[:7]
    assert path.endswith("jsonl.gz")
    hash_path = path[:-9] + f".warc_{short_md5}" + ".jsonl.gz"

    cmd = f"aws s3 cp {path} {os.path.join(args.dest_dir, month, os.path.basename(hash_path))}"
    if not args.use_aws_cli:
        cmd  = cmd.replace("aws s3 cp", "cp")

    if args.verbose:
        print(cmd)

    cmds.append(cmd)

with open(args.output, 'w') as f:
    f.write("\n".join(cmds))
