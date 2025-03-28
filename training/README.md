## Running Training Experiments

This folder contains code for running the training scripts we used in TiC-LM. To provide a high-level overview

- `continual_run.py` is the entrypoint for the training code which wraps around `open_lm` by generaeting commands for running sequential training jobs across months.

- `training_setup.sh` contains a short script which clones `open_lm`, applies our patch file (`open_lm.patch`) to be able to run some continual methods (e.g., EWC), and installs dependencies.

- `configs` contains configurations for the different scales. The 220B token scale that we report in our paper corresponds to `3b-2x.yaml` and the 440B scale corresponds to `3b-6x.yaml`.


---

### Setup steps

Our `continual_run.py` script generates and runs training commands for `open_lm`. For multi-node jobs, it does so via generating `torchrun` commands which requires you to (1) coordinate the setting of environment variables `NUM_NODES` and `NODE_RANK` on each node (as these will be used to correctly configure `torchrun` commands); (2) run `training_setup.sh` to clone, patch, and install `open_lm`. For illustration, each node should be setup to run the following setup steps:

```bash
# Assumes you have already cloned this repo (or your fork of it) and are in the training/ directory
git clone https://github.com/apple/ml-tic-lm tic-lm
pushd tic-lm/training
./training_setup.sh

# Set these up dynamically on your nodes, similarly to when using torchrun
export NUM_NODES = "<TOTAL_NODES_USED>"
export NODE_RANK = "<RANK_FOR_SPECIFIC_NODE>"
```

#### Downloading Oracle models

We provide the Oracle models trained up to the months `{201305, 201501, 201701, 201901, 202101, 202301, 202407}` and make them available to download from the [URLs listed here](model_checkpoints_urls.txt).

In our paper, these models make up the "Oracle Series" that serve as an important baselines for continual runs. Additionally, the `201305` model is used as the initialization for continual runs and the `202407` model is used to normalize results. However, you may certainly choose to use different models for initialization and normalization in your work. The rest of the README assumes you have downloaded these checkpoints to `<YOUR_ORACLE_COPIES>`. Note that it is crucial that for each Oracle model, you maintain the file structure as we have it, as in the below sample download script.

```bash
# Will download locally to path "./oracles" and then copy over to S3

# 14 gives you maximum parallelism (since 14 files) but you may need to reduce based on your machine
NUM_PROCESSES=14
REMOTE_PATH="<YOUR_ORACLE_COPIES>"

# Single threaded download (commented out)
# wget -i model_checkpoints_url.txt -x --cut-dirs 3

# Multi-threaded download
cat model_checkpoints_url.txt | xargs -P ${NUM_PROCESSES} -n 1 wget -x --cut-dirs=3

# Sync to S3
aws s3 sync oracles/ ${REMOTE_PATH}
```

Also note that in terms of file sizes, the whole model series is roughly 80GB, with each model being around 11GB. To replicate the training setup from our paper, you only need to download the 201305 model.

```bash
wget https://ml-site.cdn-apple.com/models/tic-lm/oracles/201305/params.txt -x --cut-dirs 3
wget https://ml-site.cdn-apple.com/models/tic-lm/oracles/201305/checkpoints/epoch_21.pt -x --cut-dirs 3
```

### Using `continual_run.py` for continual training runs

An example run of `continual_run.py` looks as follows. For multi-node jobs, this would also be run on each node (similarly to when directly using `torchrun`).

```bash
# Fill these in and make sure these paths end in "/"
tic_cc_data_path="<PATH_TO_YOUR_DATA>"
output_sync_path="<PATH_TO_SYNC_MODEL_CKPTS>"

# For our experiments, make sure this points to the 201305 Oracle
oracles_copy_path="<YOUR_ORACLE_COPIES>/201305"

# Command for Cyclic Cosine
python continual_run.py \
    --config configs/3b_2x.yaml \
    --parent-dataset-manifest ${tic_cc_data_path} \
    --exp-name "<YOUR_EXP_NAME>" \
    --accum-freq 1 \
    --multi-node \
    --warmup-usage all \
    --delete-previous-logs \
    --try-balanced-manifest \
    --init-ckpt ${oracles_copy_path} \
    --suffixes manifest.jsonl \
    --starting-timestep 201312 \
    --lr 0.0001 \
    --remote-sync ${output_sync_path}
```

Key arguments to this script include

* `--config`  which specifies the base configuration that contains default hyperparameter and scale-specific settings. We use `3b_2x.yaml`, `3b_6x.yaml` for the results in our paper
* `--parent-dataset-manifest` is the path to your tokenized data and should be set to the parent folder that contains your sequence of monthly datasets (i.e., ideally the path that contains the `201305/`, `201312/`, ... `202407/` folders).
* `--exp-name` should be a unique (human-readable) name for your run that will dictate where output checkpoints get saved
* `--remote-sync` specifies a remote directory (e.g., S3 path) to sync your checkpoints to (allowing for resumptions). The checkpoints will end up at `{remote-sync}/{exp-name}`.
* `--init-ckpt` is the path to a fixed initialization which is the path that contains both the checkpoints
* `--accum-freq` sets the gradient accumulation, which may be needed depending on your specific cluster and GPUs.
* `--multi-node` turns on multi-node training by generating commands that use `torchrun`

Another set of important arguments modifies the hyperparamters used in the continual run such as learning rate. Some arguments are specific to certian methods (e.g. EWC). We go over some important ones in this README while the `argparse` parser in `continual_run.py` contains the full set.

For all methods
* `--lr` defines the maximum learning rate in each round (for cyclic schedules)
* `--warmup` defines the per-round warmup
* `--use-ar-schedule` uses an autogressive meta-schedule across training rounds
* `--lr-scheduler` allows for changing the per-round learning rate schedule within `open_lm`, which can now be set to `rsqrt` after applying our patch
* `--lr_rsqrt_cooldown` configures the cooldown period in each round which is an additional hyperparameter for the `rsqrt` schedule
* `--optimizer` allows for changing the `optimzier` within `open_lm`, which can now be set to `schedulefree` after applying our patch. Note that when using this optimizer, you should use `--lr-scheduler const`

For EWC
* `--ewc-weight` is required to turn on usage of EWC and corresponds to the weight given to the regularization term
* `--ewc-num-iterations` configures the number of approximation steps used to compute the Fisher matrix

For LwF
* `--lwf-weight` is required to turn on usage of LwF and corresponds to the weight for the KL loss term
* `--lwf-kl` when used turns on the usage of the original KL loss term and when turned off simply treats the old checkpoint's predictions as gold labels (i.e., taking the argmax)

---

### Other sample commands

Here are some sample commands for the various optimizer and regularization-based methods. In our experiments, we implemnted Replay by pre-generating versions of our monthly datasets that already mix old and new data together (see [tic_cc_processing/README.md](../tic_cc_processing/README.md) for more details). Hence, in terms of our training script, replay can be orthogonally applied with any of the below commands simply by changing the path you pass into `--parent-dataset-manifest`.

```bash
# Using an AR schedule
python continual_run.py \
    --config configs/3b_2x.yaml \
    --parent-dataset-manifest ${tic_cc_data_path} \
    --exp-name "<YOUR_COSINEAR_EXP_NAME>" \
    --accum-freq 1 \
    --multi-node \
    --warmup-usage all \
    --delete-previous-logs \
    --try-balanced-manifest \
    --init-ckpt ${oracles_copy_path}  \
    --suffixes manifest.jsonl \
    --starting-timestep 201312 \
    --lr 0.0003 \
    --use-ar-schedule \
    --remote-sync ${output_sync_path}

# Using Rsqrt
python continual_run.py \
    --config configs/3b_2x.yaml \
    --parent-dataset-manifest ${tic_cc_data_path} \
    --exp-name "<YOUR_RSQRT_EXP_NAME>" \
    --accum-freq 1 \
    --multi-node \
    --warmup-usage all \
    --delete-previous-logs \
    --try-balanced-manifest \
    --init-ckpt ${oracles_copy_path}  \
    --suffixes manifest.jsonl \
    --starting-timestep 201312 \
    --lr-scheduler rsqrt \
    --lr 0.001 \
    --lr-rsqrt-cooldown 400 \
    --remote-sync ${output_sync_path}

# Using Schedulefree
python continual_run.py \
    --config configs/3b_2x.yaml \
    --parent-dataset-manifest ${tic_cc_data_path} \
    --exp-name "<YOUR_SCHEDFREE_EXP_NAME>" \
    --accum-freq 1 \
    --multi-node \
    --warmup-usage all \
    --delete-previous-logs \
    --try-balanced-manifest \
    --init-ckpt ${oracles_copy_path}  \
    --suffixes manifest.jsonl \
    --starting-timestep 201312 \
    --optimizer schedulefree \
    --lr 0.0001 \
    --wd 0.01 \
    --remote-sync ${output_sync_path}

# Using EWC
python continual_run.py \
    --config configs/3b_2x.yaml \
    --parent-dataset-manifest ${tic_cc_data_path} \
    --exp-name "<YOUR_EWC_EXP_NAME>" \
    --accum-freq 1 \
    --multi-node \
    --warmup-usage all \
    --delete-previous-logs \
    --try-balanced-manifest \
    --init-ckpt ${oracles_copy_path}  \
    --suffixes manifest.jsonl \
    --starting-timestep 201312 \
    --lr 0.0001 \
    --ewc-weight 10000000.0 \
    --ewc-num-iterations 100 \
    --remote-sync ${output_sync_path}

# Using LwF
python continual_run.py \
    --config configs/3b_2x.yaml \
    --parent-dataset-manifest ${tic_cc_data_path} \
    --exp-name "<YOUR_LWF_EXP_NAME>" \
    --accum-freq 1 \
    --multi-node \
    --warmup-usage all \
    --delete-previous-logs \
    --try-balanced-manifest \
    --init-ckpt ${oracles_copy_path}  \
    --suffixes manifest.jsonl \
    --starting-timestep 201312 \
    --lr 0.0001 \
    --lwf-weight 1.0 \
    --lwf-kl \
    --remote-sync ${output_sync_path}
```
