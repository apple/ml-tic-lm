# Temporal Knowledge Graph Pipeline

Extract and process temporal knowledge graphs from Wikidata dumps with Wikipedia evidence alignment.

Note: This pipeline is used for generating question-answering (QA) evaluation data.

## Table of Contents
- [Data Sources](#data-sources)
- [Pipeline Steps](#pipeline-steps)
- [Automation](#automation)
- [Output Format](#output-format)

## Data Sources

### Recent Dumps
Available directly from [Wikimedia dumps](https://dumps.wikimedia.org/wikidatawiki/):
```
https://dumps.wikimedia.org/wikidatawiki/YYYYMMDD/
```

### Historical Dumps
Available from Internet Archive:
```
https://archive.org/download/wikidatawiki-YYYYMMDD/
```

### File Format
Both recent and historical dumps use the same format:
```
wikidatawiki-YYYYMMDD-pages-articles-multistream.xml.bz2
```

## Setup
```bash
pip install -r requirements.txt
```
And Install aria2 (for fast parallel downloads)

## Pipeline Steps

### 1. Download and Extract

You can download the wikidata dumps for each avalible date like following:

```bash
# Download Wikidata dumps using aria2c (fast parallel download)
aria2c -x 16 -s 16 https://archive.org/download/wikidatawiki-YYYYMMDD/wikidatawiki-YYYYMMDD-pages-articles.xml.bz2
```

Or you can use  **`wikidata_downloader.py`** to generate a bash script that automates Wikidata dump downloads

```bash
# Download dumps from archive.org for a number of months after starting date
# Example: Download 3 months of dumps starting from January 2024
python wikidata_downloader.py \
    --start-date 20240101 \
    --num-months 3
```

To Extract content from Wikidata XML dumps: 

```bash
python -m gensim.scripts.segment_wiki -i -f wikidatawiki-YYYYMMDD-pages-articles-multistream.xml.bz2 -o wikidata-YYYYMMDD.json.gz
```

For Wikidata processing we use Gensim for extraction:
- Output is stored as compressed JSON

### 2. Generate Label Mappings

First, we need to create mappings for Q-IDs to entity labels (e.g., Q42 → "Douglas Adams") and P-IDs to property labels (e.g., P31 → "instance of"):

```bash
# Extract Wikidata labels (entities)
python wikidata_extract_label_to_id.py \
    --path wikidata-20240101.json.gz

# Combine the generated label files into a single mapping
python combine_labels.py \
    --input-dir processed_labels/wikidata20240401 \
    --output-dir wikidata_id_2_label_all

# Extract property labels from Wikidata
python wikidata_property_id2label.py
```

**Generated Files:**
- `all_id_to_label.json`: Combined entity ID to label mappings
- `wikidata_properties.json`: Property ID to label mappings

### 3. Process Knowledge Graph

```bash
# Example: Process consecutive months to get changed and unchanged triplets
python wikidata_processor_distributed.py \
    --old 20240101 \
    --new 20240201
```

### 4. Generate Cross-Platform Mappings

Before running alignment, generate mappings between Wikidata and Wikipedia:

```bash
# Map Wikidata IDs to Wikipedia titles
python wikidata_wikipedia_id_mapper.py

# Generate date mapping between platforms
python wikidata_date_matcher.py
```

**Generated Files:**
- `wikidata_id_to_wikipedia_id.json`: Cross-platform ID mappings based on English Wikipedia title matching
- `matching_intervals.json`: Maps each Wikidata interval to corresponding Wikipedia dates

### 5. Wikipedia Alignment

After generating all mappings, align with Wikipedia:

```bash
# Example: Run alignment for changed facts
python wikidata_wikipedia_aligner.py \
    --old 20240101 \
    --new 20240201 \
    --mode changed
```

The aligner:
- Maps entities between platforms
- Extracts relevant sentences
- Stores both subject-only and subject-object sentences
- Maintains ID connections

### 6. LLM-Foundry Format

Convert aligned data into evaluation format:

```bash
# Format single time period
python llm_foundry_formatter.py \
    Wikidata_datasets/20240101_20240201/changed/processed/ \
    --output jan_feb_2024

# Create stratified sample
python dataset_sampler.py \
    --input llm_foundry_processed/jan_feb_2024 \
    --num-samples 1000

# Generate YAML config for evaluation
python llm_foundry_yaml_gen.py \
    --input-file date_ranges.json \
    --output-prefix eval_config_wikidata
```

## Automation

**Important:** Set your default AWS profile before running these scripts. The automation scripts require S3 access to store and retrieve datasets.

For processing multiple time periods:

```bash
# Generate batch processing script
python script_generator_for_wikidata.py \
    --min_date 20230101 \
    --num_diffs 3
```

This generates a script that:
- Handles batched dump processing
- Manages sequential processing
- Coordinates alignment
- Cleans temporary files
- Tracks status

For handling missed dumps:
```bash
python script_generator_for_missed_dumps.py \
    --min_date 20230101 \
    --num_diffs 3
```

## Output Format

The final output for LLM evaluation is in JSON format:

```json
{
    "context": "Question: Fill in the blank: Douglas Adams' most notable work is _______. Answer:",
    "answer": "The Hitchhiker's Guide to the Galaxy",
    "aliases": ["a list of possible aliases based on the different formatting of the answer"],
    "metadata": {
        "relation": "notable work"
    }
}
```
