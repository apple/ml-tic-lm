## Obtaining the TiC-CC dataset

This folder contains scripts for constructing the TiC-CC training (and evaluation) datasets, building upon the assets released by [DataComp-LM (DCLM)](`https://data.commoncrawl.org/contrib/datacomp/index.html`) and [Common Crawl](https://commoncrawl.org/). Overall, there are four preprocessing steps to run that feed into each other sequentially:

1) [Download / extraction:](#1-downloading--extracting--splitting-raw-data) Here we obtain the "raw" data after downloading and extracting the HTML from Common Crawl WARCs into monthly splits of text (via `resiliparse`). In this README, we assume the output destination of this step is `s3://path/to/your/raw/dataset`.


2) [RefinedWeb heuristic filters:](#2-refinedweb-heuristic-filters) We improve data quality via standard heuristic filtering following part of the DCLM-Baseline pipeline. We assume the output destination of this step is `s3://path/to/your/filtered/dataset`.


3) [Within-month deduplication:](#3-within-month-bff-deduplication) We again follow DCLM-Baseline and use their BFF procedure except we only run it within each month. This outputs to `s3://path/to/your/deduped/dataset`.

4) [Tokenizing and shuffling:](#4-tokenize-shuffle-if-using-openlm) If you wish to use our training scripts (based on [OpenLM](https://github.com/mlfoundations/open_lm)), you need to pre-tokenize and shuffle your data. We assume this outputs data to `s3://path/to/your/tokenized/dataset`.

These steps are run for both the training and evaluation sets of TiC-CC. For the domain-specific TiC-CC evaluations (i.e., News and Wikipedia), we need to run an additional step that filters for the relevant domains based upon URL.

5) [URL-based filtering for TiC-CC-Wiki and TiC-CC-News (Evals Only):](#5-tic-cc-wiki-and-tic-cc-news)


For most part, these steps assume you've first cloned our repo and are in the `tic_cc_processing` directory.

```bash
git clone https://github.com/apple/ml-tic-lm tic-lm
pushd tic-lm/tic_cc_processing
```

We elaborate on how to run each of these steps below.

---

### 1) Downloading / extracting / splitting raw data

The starting point for our dataset are the WARC records released by Common Crawl (CC), which contain the HTML content from the pages crawled by CC. To use this data in our pipeline, we need to perform the following:
- Extract raw text from HTML (using `resiliparse`) and organize the documents into the `jsonl` format.
- Split the `jsonl` files along two dimensions: (1) temporally based upon dump date; (2) holding out training and evaluation splits. For the former, we use the fact that the dump date is indicated by filename. For the latter, we randomly assign all Common Crawl paths into 10 uniformly sampled and equally sized "global shards".  In our paper, we use global shard `01` for training and `10` for evaluation.

For most of the data (all pre-2023 CC dumps) that we use in TiC-LM, we can leverage the fact that DCLM has already performed the download and extraction steps in their release of DCLM-Pool. For the new dumps between Jan-2023 and Jul-2024, we will need to run DCLM's ray-based download/extraction script.

#### Pre-2023 Common Crawl Dumps (May-2013 to Dec-2022)

For data that comes from pre-2023 Common Crawl (CC) dumps, we directly download a subset of files from [DCLM-Pool](https://data.commoncrawl.org/contrib/datacomp/index.html) hosted on Common Crawl's S3 bucket (free of charge). We list the relevant files for our training and evaluation sets in [download/pre2023/](download/pre202301/) and include example scripts that can be modified to point to your desired destination.

Specifically, [run_pre2023_download.sh](download/pre202301/run_pre2023_download.sh) (copied below) first runs `generate_copy_cmds` which  generates a file of commands that can be applied with the [`s5cmd`](https://github.com/peak/s5cmd) (i.e, `s5cmd run <commands_file.txt>`). This will by default group files by date into subfolders `s3://path/to/your/raw/data/gs_<GS>_of_10/<YYYYMM>` where `<GS>` and `<YYYYMM>`  indicates the global shard and dump month IDs respectively. If you do not already have `s5cmd` on your machine you may simply install it with `pip`.

     pip install s5cmd

Note that to run this, it involves first retrieving the files containing the
right sets of paths, stored at
[train](https://ml-site.cdn-apple.com/datasets/tic-lm/pre2023_cc_paths/dclm_pool_paths_gs_01_of_10.txt)
and [test](https://ml-site.cdn-apple.com/datasets/tic-lm/pre2023_cc_paths/dclm_pool_paths_gs_10_of_10.txt).


```bash
# Change dest_dir to where you'd like to store your dataset
dest_dir="s3://path/to/your/raw/data"

# We use only these two global shards in our paper
for gs in 01 10
do
    wget https://ml-site.cdn-apple.com/datasets/tic-lm/pre2023_cc_paths/dclm_pool_paths_gs_${gs}_of_10.txt

    dest_dir = ${parent_dest_dir}/gs_${gs}_of_10

    # Generate commands file
    python generate_copy_cmds.py --input dclm_pool_paths_gs_${gs}_of_10.txt --dest-dir ${dest_dir} --output copy_cmds_gs_${gs}.txt

    # Run copies with s5cmd (can comment out if you want to run only cmd generation)
    s5cmd --retry-count 20 --log error --stat run copy_cmds_gs_${gs}.txt | tee s5cmd_log_gs_${gs}_of_10.txt | tail -n 4
done
```

Notes:
- When reading from the Common Crawl bucket, you will need to use a valid set of AWS credentials (e.g., `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`) though your account should not be charged.
- `s5cmd` is the default (and preferred) way to actually run the copying. By default, the run command shared above will summarize the copy success rate upon finishing and log the commands resulting in errors to a text file. For global shards `01` and `10` you should see `507983` and `508277` successes respectively.
- If you run into trouble with `s5cmd` and wish to instead use `aws-cli`, you can run `generate_copy_cmds.py` with the `--use-aws-cli` flag. For now, we do not provide a script to run copies with `aws-cli` but can create one if needed by multiple users.

#### Post-2023 Common Crawl Dumps (Jan-2023 to Jul-2024)

For data between January-2023 and July-2024, we need to first re-use a lightly modified version of DCLM's [download/extraction script](download/post202301_pre202407/process_common_crawl_w_ray.py) to extend DCLM-Pool by downloading and extracting the [relevant files from Common Crawl ](download/post202301_pre202407/cc_paths/). In particular, to create the training and evaluation splits for TiC-CC, we can pass in pre-computed file lists that we provide in [download/post202301_pre202407/cc_paths/](download/post202301_pre202407/cc_paths/) to `--json_file_path` as shown below in [run_post2023_download.sh](download/post202301_pre202407/run_post2023_download.sh):

```bash
parent_dest_dir="s3://path/to/your/raw/data"

for gs in 01 10
do
    dest_dir=${parent_dest_dir}/gs_${gs}_of_10
    python process_common_crawl_w_ray.py \
        --json_file_path cc_paths/CC_paths_${gs}_of_10.json.gz \
        --output_path ${dest_dir} \
        --extractor resiliparse \
        --ray_num_cpus 2
done
```

This script makes use of `ray` for highly-parallelized execution across multiple CPU compute nodes. Thus, using it first requires launching a ray-cluster before logging into the head node to run the script. More detailed instructions can be found [here](https://github.com/mlfoundations/dclm/tree/main?tab=readme-ov-file#ray-based-filtering-and-cleaning) for cluster launching and management. We also provide a [sample cluster configuration](download/post202301_pre202407/cluster_extraction_config.yaml) (for EC2) that you can use after adapting to your needs (e.g., filling in your AWS credentials).

---

### 2) RefinedWeb heuristic filters

We use the [data processing code from the dclm repository](https://github.com/mlfoundations/dclm/tree/main/baselines) to run the RefinedWeb heuristic filters on our dataset, as specified by their [dclm_baseline_refinedweb.yaml](https://github.com/mlfoundations/dclm/blob/main/baselines/baselines_configs/dclm_baseline_refinedweb.yaml). The most detailed documentation on how to use data processor from DCLM is provided [here](https://github.com/mlfoundations/dclm/tree/main/baselines#running-the-processing-pipeline).

For this step, we also provide a significantly cheaper (preferred) way to run these cleaning steps, based upon pre-computed IDs for the pages that are kept (which circumvents needing to re-run the actual logic of the filters themselves). In either case, the core workflow is the same, involving the following steps:

(1) Clone thte `dclm` repo and create a reference json in `exp_data/datasets/untokenized/tic_cc_raw.json` within it. Make sure to change the `dataset_url` field to correspond to where your data is stored.

```json
{
    "uuid": "c5fd5803-49de-4a73-8e07-52d628d3d920",
    "name": "tic_cc_raw",
    "creation_date": null,
    "dataset_url": "s3://path/to/your/raw/data/",
    "manifest_url": null,
    "sources": [],
    "tokenized": false,
    "tokenizer": null,
    "num_tokens": null,
    "size": null,
    "dcnlp_commit_hash": null,
    "dcnlp_diff": null,
    "data_key": "jsonl"
}
```

Note that the `uuid` is hardcoded to be a value that is unique from other existing `uuids` in the `dclm` repository. The particular choice for this (along with having accurate values for other keys like `creation_date`) do not really matter for our purposes.

(2) Launch a ray cluster following DCLM's [setup
instructions](https://github.com/mlfoundations/dclm/tree/main/baselines#setting-up-a-ray-cluster).
If you wish to use our preferred ID-based approach, you need to include setup
commands to both (i) patch the public DCLM repo with the changes provided in
[dclm_ticlm.patch](./dclm_ticlm.patch); (ii)  download our dump of kept IDs
which are hosted here [https://ml-site.cdn-apple.com/datasets/tic-lm/rw_ids].

```bash
# Assume you have cloned this repo and are in the tic_cc_processing/ dir

# Apply our provided patch to the DCLM repo
git clone https://github.com/mlfoundations/dclm.git
cp dclm_ticlm.patch dclm && pushd dclm
git checkout 6cf1ff4c35b7c2fd97ef27309a0ba3beb6c340f0
git apply dclm_ticlm.patch
pip install requirements.txt
pip install -e .

# Untar each month in parallel (change NUM_CPUS_PER_NODE depending on your compute nodes)
mkdir -p tic-lm-rw-filtering-ids
pushd tic-lm-rw-filtering-ids

# Download all indices
# Single threaded download
# wget -i ../../rw_ids_urls.txt
# Multi-threaded download
aria2c -x 16 -i ../../rw_ids_urls.txt

NUM_CPUS_PER_NODE=32
find . -name "*.tar.gz"   | xargs -P ${NUM_CPUS_PER_NODE} -I {} tar -xf {}
find . -name "*.tar.gz"   | xargs -P ${NUM_CPUS_PER_NODE} rm
find . -type f -name "*.txt" -path "./*" | xargs -P ${NUM_CPUS_PER_NODE} -I {} mv {} . && find . -type d -empty | xargs -P ${NUM_CPUS_PER_NODE} rmdir

popd
popd
```

Please note that this assumes each node in your ray cluster has enough storage to house all the IDs (about 200GB). If this is not possible, the alternative is run this set of commands once and to upload the set of IDs to S3. In the following step when you actually run the filtering, you would then need to pass in the S3 path where your IDs are stored.


(3) Log into the head node of the ray cluster and run the following command. To run our (preferred) method which uses pre-computed IDs, set `<YAML_CONFIG>=refinedweb_ids_plus_mods.yaml`. To run the actual logic of the filtering/cleaning operations, use `dclm_baseline_refinedweb.yaml`.

```bash
python ray_processing/process.py \
    --source_ref_paths exp_data/datasets/untokenized/tic_cc_raw.json \
    --readable_name tic_cc_rw_filtered \
    --output_dir s3://path/to/your/filtered_data/ \
    --config_path baselines/baselines_configs/refinedweb_ids_plus_mods.yaml \
    --source_name cc
```

If you do use `refinedweb_ids_plus_mods.yaml`, you'll need to first modify the `ids_dir` argument for the `warc_metadata_filter_parallel_dir` step (copied below) to point to where you downloaded the IDs to.

```yaml
- func: warc_metadata_filter_parallel_dir
  ids_dir: /absolute/path/to/your/ids/copy/  # Modify to your ids location
  metadata_keys: ["WARC-Record-ID", "WARC-Date"]
  ignore_chars: ["<urn:uuid:", ">"]
```

---

### 3) Within-month BFF deduplication

Since the assumption is that we do not get all data up front in continual setups, we want to dedupliate within each month to simulate a more realistic data collection / processing setup. The deduplication follows DCLM and uses a rust-based script. You can perform the setup for deduplication using `deduplication/dedup_monthly_setup.sh`.

    cd deduplication

    bash dedup_monthly_setup.sh

This setup script will clone the repo for running BFF dedups and compiling the source code (written in rust). Once everything is set up, you can just change the destination directory within `dedup_monthly.sh` before running it.

    bash dedup_monthly.sh

----

### 4) Tokenize-Shuffle (If using OpenLM)

If using our OpenLM-based training code, you should pre-tokenize and shuffle all the training data *separately for each month.* Here, following the [DCLM documentation](https://github.com/mlfoundations/dclm/tree/main?tab=readme-ov-file#3-tokenization-and-shuffling) there are both a ray-based implementation as well as a rust-based implementation. Generally, the latter is recommended as it is more cost-efficient.

Our training script expects the data to be in the following format

```
s3://path/to/your/tokenized/dataset/
    201305/
        00000001.tar
        00000002.tar
        ⋮
        manifest.jsonl
    201312/
        00000001.tar
        00000002.tar
        ⋮
        manifest.jsonl
    ⋮
    202407/
        00000001.tar
        00000002.tar
        ⋮
        manifest.jsonl
```

We provide example scripts in [tokenize_shuffle/](tokenize_shuffle/) that wrap around the DCLM tokenize-shuffle scripts, calling it separately for each month. You may parallelize this across multiple nodes by simply running different months on each node.

### Rust-based

This script runs only on a single CPU node. More documentation about requirements is provided [here](https://github.com/mlfoundations/dclm/tree/main/rust_processing/tokshuf-rs).

```
cd tokenize_shuffle

# Setup script
./setup_tokenize_shuffle_rust.sh

# Run script
./tokenize_shuffle_rust_monthly.sh
```

### Ray-based

This first requires setting up a ray-cluster, similar to RefinedWeb filtering. Then after logging into your head node, you just need to run [./tokenize_shuffle_ray_monthly.sh](./tokenize_shuffle_ray_monthly.sh).

---

### 5) TiC-CC-Wiki and TiC-CC-News

For the TiC-CC-Wiki and TiC-CC-News evaluations, we need to run an additional set of filters. Similarly to the ID-based RefinedWeb filtering, we provide this functionality in our patch file for the DCLM repo. Thus, in your cluster configuration, you need to include the patching command as shown earlier

```bash
# Assume you have cloned this repo and are in the tic_cc_processing/ dir

# Apply our provided patch to the DCLM repo
git clone https://github.com/mlfoundations/dclm.git
cp dclm_ticlm.patch dclm && pushd dclm
git checkout 6cf1ff4c35b7c2fd97ef27309a0ba3beb6c340f0
git apply dclm_ticlm.patch
```

Then, to perform this step we largely follow the same steps as for RefinedWeb filtering except you now
* Use the output of Step 4 (Deduplication) as the starting point instead of the output of Step 2. This requires creating a new `exp_data` JSON file that points to `s3://path/to/your/deduped/data/`.
* Select `domain_extraction_wiki.yaml` and `domain_extraction_news.yaml` as the <YAML_CONFIG> file for the DCLM data processor and choose new paths for the outputs to be written to.

Note this only needs to be run on the evaluation shard (i.e. global shard 10). Furthermore, to replicate the evaluations we ran in our paper, it also only needs to be run on the following set of months specified in [first_per_year.txt](../evaluation/first_per_year.txt). This can be done using `--shard_list_filters "201305/" "201403/" "201501/" "201602/" "201701/" "201801/" "201901/" "202001/" "202101/" "202201/" "202301/" "202402/" "202407/"` in the `process.py` script within `dclm`.
