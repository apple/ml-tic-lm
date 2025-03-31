# StackExchange Data Processing Project

This project processes large StackExchange data dumps, converting them into structured formats suitable for machine learning tasks. The project creates monthly snapshots of questions and answers, converting them into two-choice format where the correct answer is the accepted answer and the wrong choice is the answer with the lowest votes that appeared before the accepted answer. The output is formatted for LLM-Foundry evaluation pipelines.

## Getting Started

## Dependencies

Install 7zip:
```
apt install p7zip-full
```

### Data Download

1. Visit the Internet Archive's StackExchange data dump: https://archive.org/details/stackexchange, at the time we downloaded the data, the last modified date of the files were 07-Apr-2024.
2. Download the relevant community data files (they are in 7z format).  In the 
   paper, we mainly focus on StackOverflow and Math categories. For testing, 
   start with a smaller category such `ai` first.
3. Organize the downloaded files in the following structure:
   ```
   src_data/
   ├── math/
   │   └── math.stackexchange.com.7z
   └── stackoverflow/
       ├── stackoverflow.com-Posts.7z
       ├── stackoverflow.com-PostHistory.7z
       └── stackoverflow.com-Comments.7z
   ```

## Automated Processing Pipeline

The main script `generate_stackexchange_processor.py` orchestrates the entire data processing pipeline:
- Generates a bash script for processing multiple StackExchange communities in parallel
- Manages disk space efficiently by processing communities in batches
- Handles extraction, conversion, and vote-based filtering
- Creates monthly snapshots with two-choice format (accepted answer vs lowest-voted early answer)
- Formats output for LLM-Foundry evaluation pipelines

Usage: 
```bash
python generate_stackexchange_processor.py \
  --src-data src_data/ --dst-data parsed_stackexchange_data \
  --s3-path <s3-path-to-upload>/tic-lm/eval_data/stackexchange/
bash process_stackexchange_dumps.sh
```

The script uploads the parsed StackExchange data for each category to S3 and 
removes it from local directory. To run the evaluations, the data is expected 
to exist in the following paths relative to the root of the repository:
```bash
tic_stackexchange_local_path="local_data/stackexchange"
```

The scripts upload the data to S3 and remove the local copy. To download, run 
the following commands:
```bash
mkdir -p evaluation/local_data/stackexchange/
aws s3 cp <s3-path-to-upload>/tic-lm/eval_data/stackexchange/  evaluation/local_data/stackexchange/ --recursive
```



## Pipeline Components

1. **XML to JSONL Conversion**
   - Script: `stackexchange_xml_to_jsonl.py`
   - Converts Posts.xml to JSONL format
   - Usage: `python stackexchange_xml_to_jsonl.py --input_xml <Posts.xml> -o <output_dir>`

2. **Post History Processing**
   - Script: `process_post_history_multiprocess.py`
   - Processes PostHistory.xml using parallel processing
   - Usage: `python process_post_history_multiprocess.py --input_file <PostHistory.xml> --output_dir <output_dir>`

3. **Monthly Snapshot Creation**
   - Script: `create_monthly_snapshots_accepted_answers.py`
   - Creates chronological snapshots with accepted answers
   - Usage: `python create_monthly_snapshots_accepted_answers.py --input_path <posts_dir> --post_history_path <history_dir> --output_path <output_dir>`

4. **Vote Processing and LLM Format Conversion**
   - Script: `format_qa_pairs_with_votes.py`
   - Adds vote metadata and converts to LLM Foundry format
   - Usage: `python format_qa_pairs_with_votes.py --input-dir <input_dir> --votes-file <votes.json>`

5. **Data Filtering and Truncation**
   - Script: `truncate_tokensize_sampled_votebased.py`
   - Filters based on vote differences and truncates to token limits (e.g. query: 1300, total: 1900)
   - Usage: `python truncate_tokensize_sampled_votebased.py <input_dir> [--output_dir <output_dir>]`

6. **Data Aggregation**
   - Script: `aggregate.py`
   - Combines monthly data into larger chunks
   - Creates files with 500 samples each

7. **LLM Foundry Configuration**
   - Script: `llm_foundry_yaml.py`
   - Generates YAML configuration for evaluation

## Data Quality Criteria

The project implements several quality filters:
- Clear winner identification (vote difference ≥ 4 and ratio ≥ 4)
- Token length limits for LLM compatibility
- Minimum sample size requirements

