# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
# 

"""
Script to take a collection of jsonls (or compressed version of same)
and reshard them such that there's more documents/file in the end.

Note this will RENAME files, so we'll lose history of how files get mapped here (but the stats will get carried over)
"""

import ray
import boto3
import glob
import os
from cloudpathlib import S3Path
import gzip
import zstd
import json
from pathlib import Path
import argparse
import random

DEFAULT_SUFFIXES = ['.jsonl', '.jsonl.zstd', '.jsonl.zst', '.jsonl.gz']

# ================================================
# =                  Utilities                   =
# ================================================

@ray.remote
class GlobalCounter:
    # shared threadsafe counter object
    def __init__(self):
        self.counter = 0


    def get_count(self):
        cur_val = self.counter
        self.counter += 1
        return cur_val


def collect_filenames(base_input_path, suffixes=None):
    """ Collects full filenames from s3/local 
        base_input_path should NOT point to any stats
    """
    suffixes = suffixes if suffixes != None else DEFAULT_SUFFIXES
    if base_input_path.startswith('s3://'):
        s3 = boto3.resource("s3")
        bucket_name, path_within_bucket = base_input_path.replace("s3://", "").split("/", 1)
        bucket = s3.Bucket(bucket_name)
        files = [x.key for x in bucket.objects.filter(Prefix=path_within_bucket)]
        files = ['s3://%s' % os.path.join(bucket_name, _)
                 for _ in files if any(_.endswith(s) for s in suffixes)]
    else:
        if suffixes == None: 
            suffixes = ''
        files = []
        for suff in suffixes:
            files.extend(glob.glob(os.path.join(base_input_path, '**/*%s' % suff), recursive=True))

    return files


def write_lines(lines, output_filename):
    """ Takes a bunch of lines (already bytestrings) and globs them together and puts them on S3 (or locally).
    """
    if output_filename.startswith('s3://'):
        fh = S3Path(output_filename).open('wb')
    else:
        Path(os.path.dirname(output_filename)).mkdir(parents=True, exist_ok=True)
        fh = open(output_filename, 'wb')

    lines = [line.encode('utf-8') if isinstance(line, str) else line 
             for line in lines]
    doc = b'\n'.join(lines)
    if output_filename.endswith('zstd') or output_filename.endswith('zst'):
        doc = zstd.compress(doc)
    if output_filename.endswith('.gz'):
        doc = gzip.compress(doc)
    fh.write(doc)

    fh.close()
    return len(lines) # Just return something informative?


def all_eq(els):
    return all(el == els[0] for el in els)


def as_number(x):
    if isinstance(x, (bool, int, float)):
        return x		
    try:
        return int(x)
    except ValueError:
        pass
    try:
        return float(x)
    except ValueError:
        pass
    return x
    


# ================================================
# =                  Mapper block                =
# ================================================


def base_chunk_mapper(batch: dict, base_dir:str, output_base_dir:str, counter:GlobalCounter, output_prefix:str,
                      ignore_stats_errs:bool, skip_stats_merge:bool, subsample_rate:float=None, extension='gz'):
    """ Concatenates a batch together, writes it to output_prefix, and merges the stats appropriately
    """
    
    count = ray.get(counter.get_count.remote())
    if skip_stats_merge:
        output_filename = os.path.join(output_base_dir, f'CC_%s_%08d.jsonl.{extension}' % (output_prefix, count)) # zstd by default
    else:
        output_filename = os.path.join(output_base_dir, 'processed_data', '%s_%08d_processed.jsonl.gz' % (output_prefix, count)) # zstd by default

    # Merge the data and write to correct file
    raw_data = []
    orig_num_lines = 0
    for filename in batch['item']:
        print(filename)
        # Read from s3 
        if filename.startswith('s3://'):
            data = S3Path(filename).open('rb').read()
        else:
            data = open(filename, 'rb').read()
        
        if os.path.splitext(filename)[-1] == '.zstd': 
            data = zstd.decompress(data)

        lines = data.splitlines()
        orig_num_lines += len(lines)
        if subsample_rate != None:
            lines = [_ for _ in lines if random.random() < subsample_rate]
        raw_data.extend(lines)
        
    num_lines = write_lines(raw_data, output_filename)
    if orig_num_lines != num_lines and subsample_rate is None:
        print(f"WARNING: Only wrote {num_lines} from {orig_num_lines} original lines")

    if not skip_stats_merge:
        # Merge the stats and write to s3
        batch_stats_filenames = [get_stats_filename(p, base_dir) for p in batch['path']]
        output_stats_filename = get_stats_filename(output_filename.replace('s3://', ''), output_base_dir)

        try:
            merged_stats = [_ for _ in merge_stats(batch_stats_filenames) if _ != False]
            write_lines(merged_stats, output_stats_filename)
        except Exception as err:
            if ignore_stats_errs == True:
                pass
            else:
                raise err

    return {'num_lines': [num_lines]}
    

def get_stats_filename(data_filename, base_dir):
    """ Given a filename of some data, and the base dir, gets the filename of the local_stats 

    e.g. 'foo/bar/processed_data/ack/baz_processed.jsonl.zstd', 'foo/bar/'
    -> 'foo/bar/stats/ack/baz_stats.jsonl'
    """


    stats_dir = os.path.join(base_dir, 'stats')
    base_dir_s3less = base_dir.replace('s3://', '')
    # Get part of data_filename that happens AFTER processed_data
    stats_filename = '^%s#' % data_filename
    stats_filename = stats_filename.replace('^%s' % os.path.join(base_dir_s3less, 'processed_data/'), '')
    assert not stats_filename.endswith('/')

    # Now replace the suffix of the stats filename
    valid_suffices = ['.jsonl#', '.jsonl.gz#', '.jsonl.zstd#', '.jsonl.zst#']	
    assert any(stats_filename.endswith(s) for s in valid_suffices)
    for s in valid_suffices:
        stats_filename = stats_filename.replace(s, '')	

    if stats_filename.endswith('_processed'):		
        stats_filename = stats_filename[:-len('_processed')]
    stats_filename = stats_filename + '_stats.jsonl'

    return os.path.join(stats_dir, stats_filename)


def merge_stats(stats_files):
    """ Takes in a list of filenames for the stats files and merges them together.

    Either uploads successfully merged stats or returns False
    """
    # Step 1: Gather all stats_files
    all_stats = []
    for stats_file in stats_files:
        if stats_file.startswith('s3://'):
            stats_file_data = S3Path(stats_file).open('rb').read()
        else:
            stats_file_data = open(stats_file, 'rb').read()
        all_stats.append([json.loads(_) for _ in stats_file_data.splitlines()])

    # Step 2: Check to see if all stats are well formed
    #         (I'm too stupid to figure out how to merge if things are problematic)

    if not all_eq([len(_) for _ in all_stats]): # check stats all same len
        return False

    for i in range(len(all_stats[0])):
        if not all_eq([stat[i]['name'] for stat in all_stats]):
            return False


    # Step 3: Group and merge all stats
    try:
        stats_groups = [[stat[i] for stat in all_stats] for i in range(len(all_stats[0]))]
        merged_stats = [json.dumps(_merge_stats_row(stat_group)) for stat_group in stats_groups]
        merged_stats.append(json.dumps({'name': 'reshard', 'num_shards': len(stats_files)}))		
        return merged_stats
    except Exception as err:
        return False



def _merge_stats_row(stats):
    """ Actual thought goes in here. 

    Stats is a list of dicts with the same key
    General policy looks like:
    - 'name' gets copied directly
    - all numerics get SUMMED, except for specific average things called out explicitly
    - all booleans get AND-ed
    - all else get CONCATENATED
    """

    if not all_eq([set(_.keys()) for _ in stats]):
        raise ValueError("Stats have inconsistent keys!", stats)
    keys = stats[0].keys()
    output = {}

    for k in keys:
        if k == 'name': # Name case
            output[k] = stats[0][k]
        elif isinstance(stats[0][k], bool):
            output[k] = all(stat[k] for stat in stats) 

        elif isinstance(as_number(stats[0][k]), (float, int)):
            if k == "secs/page":
                total_secs = sum(as_number(stat['total_secs']) for stat in stats)
                total_pages = sum(as_number(stat['pages_in']) for stat in stats)
                output[k] = total_secs/total_pages
            else:
                output[k] = sum(as_number(stat[k]) for stat in stats)
        else:
            output[k] = [stat[k] for stat in stats]
    return output



# =================================================
# =                  Main Block                   =
# =================================================

def main(base_dir, output_base_dir, batch_size, output_prefix, suffixes=None, debug_max_files=None,
         ignore_stats_errs=False, skip_stats_merge=False, subsample_rate=None, extension='gz', paths_from_file=None, num_cpus=1):

    # Step 0: Initialize Ray + Counter
    ray.init(ignore_reinit_error=True)
    counter = GlobalCounter.remote()

    # Step 1: Collect filenames into dataset
    if paths_from_file is not None:
        with open(paths_from_file, 'r') as f:
            shard_filenames = f.read().splitlines()
    elif base_dir.startswith("s3:") and S3Path(os.path.join(base_dir, 'processed_data')).exists():
        shard_filenames = collect_filenames(os.path.join(base_dir, 'processed_data'), suffixes=suffixes)
    else:
        shard_filenames = collect_filenames(base_dir, suffixes=suffixes)

    if debug_max_files != None:
        shard_filenames = shard_filenames[:debug_max_files]


    print("Collected %s files to reshard" % len(shard_filenames))		

    # Don't read the binary fiiles first. Instead just pass the filenames
    #ds = ray.data.read_binary_files(shard_filenames, include_paths=True)
    ds = ray.data.from_items(shard_filenames)

    # Step 2: map to reshard worker
    ds = ds.map_batches(base_chunk_mapper, batch_size=batch_size,
                   fn_kwargs={'base_dir': base_dir,
                                 'output_base_dir': output_base_dir,
                                 'counter': counter,
                                 'output_prefix': output_prefix,
                                 'ignore_stats_errs': ignore_stats_errs,
                                 'skip_stats_merge': skip_stats_merge,
                                 'subsample_rate': subsample_rate,
                              'extension': extension},
                    num_cpus=num_cpus
                   ).materialize()


#TODO: make main_integrated and add to global functions


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-dir', type=str, required=True)
    parser.add_argument('--output-base-dir', type=str, required=True)
    parser.add_argument('--batch-size', type=int, required=True)
    parser.add_argument('--output-prefix', type=str, default='shard')
    parser.add_argument('--suffixes', nargs='+') 
    parser.add_argument('--ignore-stats-errs', action='store_true')
    parser.add_argument('--skip-stats-merge', action='store_true')
    parser.add_argument('--subsample-rate', type=float)
    parser.add_argument('--debug-max-files', type=int)
    parser.add_argument('--extension', type=str, default="zst")
    parser.add_argument("--paths-from-file", type=str, default=None)
    parser.add_argument("--num-cpus", type=int, default=1)
    parser.add_argument("--ray_spill_location", type=str, default="/mnt/ray_tmp")

    aws_vars = {k: v for k, v in os.environ.items() if k.startswith("AWS")}
    runtime_env = {"env_vars": aws_vars}

    args = parser.parse_args()
    ray.init(
        runtime_env=runtime_env,
        _temp_dir=args.ray_spill_location,
    )

    main(base_dir=args.base_dir,
         output_base_dir=args.output_base_dir,
         batch_size=args.batch_size,
         output_prefix=args.output_prefix,
         suffixes=args.suffixes,
         debug_max_files=args.debug_max_files,
         ignore_stats_errs=args.ignore_stats_errs,
         skip_stats_merge=args.skip_stats_merge,
         subsample_rate=args.subsample_rate,
         extension=args.extension,
         paths_from_file=args.paths_from_file,
         num_cpus=args.num_cpus)