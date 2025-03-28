## Running TiC-LM evaluations

This folder contains scripts for running the TiC-LM evaluations. To provide a high-level overview, our evaluations come in two forms: (1) perplexity evaluations that operate on pre-tokenized data (i.e., TiC-CC) and are executed via `open_lm` in `continual_ppl_eval.py`; (2) downstream evaluations (i.e. TiC-Wiki, TiC-Stackexchange, TiC-CodeDocs) that are run via `llmfoundry`/`composer` in `continual_downstream_eval.py`.

- `continual_eval.py` is the entrypoint for the evaluation code which is used to run both types of evaluations, by generating and running the commands for both perplexity and downstream evaluation scripts.
- `eval_configs` contains preset configurations (i.e., `yaml` files) that are specified as an argument to `continual_eval.py` to indicate which evaluations to run
- `evaluation_setup.sh` is a setup script that install dependencies (and which you may need to adapt) to be able to use `continual_eval.py`.

---

### Setting up evaluation data

For all continual evaluations, the scripts here all assume that the evaluation sets have already been created and placed in specific paths. For the TiC-CC validation sets, please modify the placeholder paths in [eval_configs/ppl_evals/] by running the following commands:

```bash
#!/bin/bash

# Change these to your own paths where you store tokenized TiC-CC heldout data
# Assumption is that these paths end in "/" and contain the subfolders "gs_10_of_10/{YYYYMM}"
tic_cc_path="s3://path/to/your/tokenized/tic_cc_data/"
tic_cc_wiki_path="s3://path/to/your/tokenized/tic_cc_news_data/"
tic_cc_news_path="s3://path/to/your/tokenized/tic_cc_wiki_data/"

for file in eval_configs/ppl_evals/*.txt; do
  echo $file
  if [ -f "$file" ]; then
    sed -i -e "s|s3://path/to/your/tokenized/tic_cc_data/|$tic_cc_path|g" "$file"
    sed -i -e "s|s3://path/to/your/tokenized/tic_cc_news_data/|$tic_cc_wiki_path|g" "$file"
    sed -i -e "s|s3://path/to/your/tokenized/tic_cc_wiki_data/|$tic_cc_news_path|g" "$file"
  fi
done
```

For instructions on how to create other downstream evaluations, please see the 
relevant directories in the root directory of this repository.
- [`tic_cc_processing`](../tic_cc_processing/) for TiC-CC evaluations
- [`tic_wiki_processing`](../tic_wiki_processing/) for TiC-Wiki
- [`tic_stackexchange_processing`](../tic_stackexchange_proecssing/) for TiC-StackExchange
- [`tic_codedocs_processing`](../tic_codedocs_processing/) for TiC-CodeDocs

Scripts for each evaluation uploads the data to S3 paths that ensures the 
scripts can run in parallel and once before evaluations. To run evaluations, 
ensure that the data is downloaded from S3 paths to the following local paths:
```
# remote paths
tic_stackexchange_path="s3://<bucket>/prefix/ml-tic-lm/evaluation/local_data/stackexchange"
tic_wiki_changed_path="s3://<bucket>/prefix/ml-tic-lm/evaluation/local_data/twiki_changed_textbased"
tic_wiki_unchanged_path="s3://<bucket>/prefix/ml-tic-lm/evaluation/local_data/twiki_unchanged_textbased"
tic_codedocs_numpy_path="s3://<bucket>/prefix/ml-tic-lm/evaluation/local_data/code_eval/numpy"
tic_codedocs_pytorch_path="s3://<bucket>/prefix/ml-tic-lm/evaluation/local_data/code_eval/pytorch"

# local paths
tic_stackexchange_local_path="ml-tic-lm/evaluation/local_data/stackexchange"
tic_wiki_changed_local_path="ml-tic-lm/evaluation/local_data/twiki_changed_textbased"
tic_wiki_unchanged_local_path="ml-tic-lm/evaluation/local_data/twiki_unchanged_textbased"
tic_codedocs_numpy_local_path="ml-tic-lm/evaluation/local_data/code_eval/numpy"
tic_codedocs_pytorch_local_path="ml-tic-lm/evaluation/local_data/code_eval/pytorch"

# copy
aws s3 cp --recursive $tic_stackexchange_path  $tic_stackexchange_local_path
aws s3 cp --recursive $tic_wiki_changed_path   $tic_wiki_changed_local_path
aws s3 cp --recursive $tic_wiki_unchanged_path $tic_wiki_unchanged_local_path
aws s3 cp --recursive $tic_codedocs_numpy_path $tic_codedocs_numpy_local_path
```

The static evaluation can simply be downloaded with `download_static_evals.sh` (which by default is already run for you within `evaluation_setup.sh`).

### Using `continual_eval.py`

`run_continual_evals.sh` is a sample script that runs all the evaluations we included in our paper for a given continual run's monthly checkpoints.

```bash
export AWS_MAX_ATTEMPTS=10
export AWS_RETRY_MODE="standard"
export PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python

ngpus=8
exp_name="YOUR_CHOSEN_EXP_NAME"
ckpt_dir="s3://path/to/your/checkpoints/dir/"
remote_eval_dir="s3://path/to/your/evaluation/dir/"

# Run continual evaluations
# Note 1: By default, TiC-CC evals are run as part of unified_tic_wiki.yaml and not the other two YAMLs
# Note 2: If you have sufficient disk space (i.e., >120GB for 3B models), you can add --keep-local-ckpts to avoid re-downloading models across evaluations
for eval_config in "unified_tic_wiki.yaml" "unified_tic_stackexchange.yaml" "unified_tic_codedocs.yaml"
do
python continual_eval.py \
 --eval_config eval_configs/${eval_config} \
 --exp-name ${exp_name} \
 --parent-ckpt-dir ${ckpt_dir}${exp_name} \
 --time-range "201305:202407" \
 --num-gpus ${ngpus} \
 --download-ppl-local \
 --ckpt-months first_per_year.txt \
 --remote-sync ${remote_eval_dir}
done

# Run static evaluations
for eval_config in "static_evals.yaml"
do
python continual_eval.py \
 --eval_config eval_configs/${eval_config} \
 --exp-name ${exp_name} \
 --parent-ckpt-dir ${ckpt_dir}${exp_name} \
 --time-range "202407:202407" \
 --num-gpus ${ngpus} \
 --download-ppl-local \
 --remote-sync ${remote_eval_dir} \
 --skip-ppl
done
```

The main arguments to use and understand are
* `--parent-ckpt-dir` points to the parent dir containing the ckpts you wish to evaluate.
* `--exp-name` is the name of the experiment, which is used to determine where the output gets written to. If not specified, it is inferred from lowest level folder in the `--parent-ckpt-dir` (TODO: We should probably add guardrails on overwriting evaluations.)
* `--remote-sync` is where your the results get copied to
* `--eval_config` is a yaml that configures the details of which evaluations should be run, most importantly naming which perplexity and downstream evals to use (which are contained via their own yaml files)
* `--ckpt-months` specifies which months of a continual run to actually evaluate (contained in a .txt file), which our paper sets to the provided `first_per_year.txt` file for our experiments. `--time-range` can be used to additionally filter which checkpoints are evaluated. If you wish to evaluate a single checkpoint (e.g. i.e., a non-continual run that does not have per-month subfolders), please remove this argument.
* `--skip-ppl` and `--skip-downstream` can be used respectively to only do one of the two types of evaluations
* `--keep-local-ckpts` allows for retaining local checkpoints, which allows you to skip re-downloading the same checkpoints when running different evaluations for the same continual run
* `--ovewrite` can be used to force evaluations to run even if previous results exist at the target remote location. By default the behavior will be that these evaluations are skipped.

Other arguments and options are provided but should not be necessary for the evaluations we ran in our paper.
