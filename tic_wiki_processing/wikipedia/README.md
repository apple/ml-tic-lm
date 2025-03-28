# Wikipedia Temporal Analysis Pipeline

This code contains tools for analyzing how Wikipedia content changes over time.  
We prepare TiC-Wiki data for evaluation using LLM-Foundry format.

Note: This pipeline is used for generating TiC-Wiki perplexity evaluation data. 

## Setup
```bash
pip install -r requirements.txt
```
And Install aria2 (for fast parallel downloads)

## Data Sources

Our scripts rely on downloading code from external sources.

Recent Wikipedia dumps are available directly from [Wikimedia 
dumps](https://dumps.wikimedia.org/enwiki/):
```
https://dumps.wikimedia.org/enwiki/YYYYMMDD/
```
Wikimedia website does not retain a fully history of Wikipedia dumps.
Historical dumps are available from Internet Archive:
```
https://archive.org/download/enwiki-YYYYMMDD/
```

Both recent and historical dumps use the same file name and format:
```
enwiki-YYYYMMDD-pages-articles-multistream.xml.bz2
```

## Core Functionality Instructions

Note: If you want to quickly generate the full dataset without understanding the underlying scripts, skip to the [Automation and Batch Processing](#automation-and-batch-processing) section below.

You need to follow the following core steps in order.

### 1. Wikipedia Dump Download

```bash
# Download Wikipedia dumps using aria2c (fast parallel download)
aria2c -x 16 -s 16 https://archive.org/download/enwiki-YYYYMMDD/enwiki-YYYYMMDD-pages-articles-multistream.xml.bz2
```

Wikipedia provides regular dumps of their content. This command efficiently downloads them using aria2c with:
- 16 connections per server (`-x 16`)
- 16 parallel downloads per file (`-s 16`)

### 2. Content Extraction

```bash
# Extract content from Wikipedia XML dumps
mkdir -p YYYYMMDD
python -m wikiextractor.WikiExtractor enwiki-YYYYMMDD-pages-articles-multistream.xml.bz2 --processes 60 --json --output YYYYMMDD

```

WikiExtractor converts Wikipedia's XML format to more manageable JSON:
- `--processes 60`: Uses 60 parallel processes for faster extraction
- `--json`: Outputs in JSON format instead of plain text


### 3. Difference Detection

```bash
# Process differences between consecutive dumps
python parse_wikipedia.py --old_month YYYYMMDD_OLDER --new_month YYYYMMDD_NEWER
```

The `parse_wikipedia.py` script performs the critical difference analysis:
- Reads articles from both old and new Wikipedia dumps
- Uses two-level diff detection (paragraph → sentence)
- Leverages Ray for distributed processing
- Outputs two CSV files:
  - `wiki_diff_YYYYMMDD_NEWER_YYYYMMDD_OLDER.csv`: Content that changed
  - `wiki_unchanged_YYYYMMDD_NEWER_YYYYMMDD_OLDER.csv`: Content that stayed the same

### 4. LLM Data Preparation

```bash
# Transform to LLM format and sample
python transform_data.py input_dir --num_samples 10000 --file_type csv

# Truncate to fit LLM context window
python truncate_data.py input_dir --max_tokens 450
```

These scripts prepare the data for LLM evaluation:
- `transform_data.py`: Converts to context/continuation JSONL format and samples
- `truncate_data.py`: Ensures text fits within LLM context windows using GPT-NeoX tokenizer

## Automation and Batch Processing

**Important:** Set your default AWS profile before running these scripts. The automation scripts require S3 access to store and retrieve datasets.

This repository includes several scripts that automate the above processes for batch execution:


### Script Generators

#### Setting Up S3 Path

For convenience, you can set an environment variable for your S3 base path:

```bash
export S3_BASE_PATH="s3://your-bucket-name"
```

1. **`download_wikipedia.py`**: Generates a bash script that automates Wikipedia dump downloads:
   ```bash
   # Generate the download script
   python download_wikipedia.py --start-date 20141106 --num-months 10 --s3-path  $S3_BASE_PATH/raw/ --concurrent-downloads 2
   
   # Run the generated script
   bash download_dumps_bash_script.sh
   ```

2. **`process_dumps.py`**: Creates a bash script to process multiple Wikipedia dumps in batches:
   ```bash
   # Generate the processing script
   python process_dumps.py  --s3-path $S3_BASE_PATH/raw/ --num-processes 60
   
   # Run the generated script
   bash process_dumps.sh
   ```
- Processed compressed dumps are stored at `$S3_BASE_PATH/temporal_wikipedia_processed_compressed`

3. **`generate_diffs.py`**: Generates a bash script for processing consecutive dump pairs:
   ```bash
   # Generate the diff processing script
   python generate_diffs.py --s3-path $S3_BASE_PATH/temporal_wikipedia_processed_compressed/
   
   # Run the generated script
   bash diffsets_script.sh
   ```
- Diff outputs are stored at `$S3_BASE_PATH/diffest_changed_wiki` and `$S3_BASE_PATH/diffest_unchanged_wiki`

The automation scripts create workflows that efficiently manage:
- Download → Extract → Process → Upload → Cleanup
- Each step runs in parallel where possible
- Temporary files are removed to conserve disk space
- Results are stored in S3 for later use

*Note: To run these scripts, you'll need to configure AWS credentials for S3 access.*

## Output Data Format

The final CSV files contain either changed or unchanged Wikipedia content between consecutive dumps. Here's an example row from `wiki_diff_20160305_20160204.csv`:

```
id,url,title,text
49104543,https://en.wikipedia.org/wiki?curid=49104543,CDM Smith,"CDM Smith is an engineering and construction company which provides solutions in water, environmental, transportation, energy, and facilities projects for public and private clients. The employee owned company is currently ranked 22nd on Engineering News-Record's ""2015 Top 500 Design Firms"" list and 13th on their ""2015 Top 200 Environmental Firms"" list. History.Camp Dresser &amp; McKee (CDM) was founded in 1947 by Thomas Camp with partners Herman Dresser and Jack McKee.In 2011, CDM acquired Wilbur Smith, a 1,000-employee transportation firm to form CDM Smith.Three years later, CDM Smith acquired the Ohio-based Louis Perry Group in late 2014 as an independent subsidiary to expand its industrial expertise in the rubber and plastic industry. In 2015, CDM Smith moved its headquarters from a 180,000 sq ft space at 50 Hampshire St, Cambridge, MA to a 120,000 sq ft office space at 75 State Street in Boston. "
```

**File Structure:**
- **Changed content files** (`wiki_diff_*.csv`): Contain text that changed between dumps
- **Unchanged content files** (`wiki_unchanged_*.csv`): Contain text that remained identical

**Column descriptions:**
- `id`: Wikipedia article unique identifier
- `url`: Direct link to the Wikipedia article
- `title`: Article title
- `text`: The text content that either changed or remained unchanged

### Evaluation Data Preparation for LLM-Foundry

After generating diffs, prepare data for LLM-Foundry evaluation, transform your csv file to jsonl digestible by llm-foundry 

```bash
# Download the CSV files from S3
aws s3 cp $S3_BASE_PATH/diffest_changed_wiki/wiki_diff_20180101_20171201.csv ./local_data/
aws s3 cp $S3_BASE_PATH/diffest_unchanged_wiki/wiki_unchanged_20180101_20171201.csv ./local_data/

# Transform and sample the CSV files, Creates ./local_data_sampled with JSONL files. 
python transform_data.py ./local_data --num_samples 10000 --file_type csv

# Truncate files to fit context windows, Creates ./local_data_sampled_truncated with truncated files.
python truncate_data.py ./local_data_sampled --max_tokens 450
```
then put the jsonl files under `ml-tic-lm/evaluation/local_data/twiki_changed_textbased/` in the repo for evaluation.

