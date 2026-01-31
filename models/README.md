
#### Downloading Oracle models

We provide the Oracle models (1B-220B and 3B-440B) trained up to the months `{201305, 201501, 201701, 201901, 202101, 202301, 202407}` and make them available to download from the [URLs listed here](model_checkpoints_urls.txt).

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

In terms of file sizes, the whole Oracle series 3B-440B is roughly 80GB (each model being around 11GB) and Oracle series 1B-220B is roughly 38GB (each model being around 5GB). To replicate the training setup from our paper, you only need to download the 201305 model.

```bash
wget https://ml-site.cdn-apple.com/models/tic-lm/oracles_3b_220b/201305/params.txt -x --cut-dirs 3
wget https://ml-site.cdn-apple.com/models/tic-lm/oracles_3b_220b/201305/checkpoints/epoch_12.pt -x --cut-dirs 3
```

The evaluation metrics for Oracle series can be found in [evals/](evals/). Please note that although we have released evaluation code, rerunning our evaluations will not give exactly the same evaluation metrics because we have not released our exact val/test sets and there is an inherent variability from subsampling the data.
