# TiC-CodeDocs

The current release of TiC-CodeDocs includes automated scripts for generating documentation for NumPy and PyTorch[^1]. The scripts follow these steps to generate and process documentation for version `v` of library `lib`:

1. Clone the library `lib`.
2. Use git releases to find the release commit for version `v`.
3. Create a standalone virtual environment (called `lib_v`) and build lib from source.
4. Generate Sphinx HTML docs.
5. Convert each of the generated HTML pages to text.
6. Postprocess the text files and create a JSONL file named `lib/{YYYY}{MM}.jsonl`.

Each line of the final JSONL file is a JSON object with `title` and `text` fields.

Note: The following scripts may break as time passes and NumPy/PyTorch changes.



------------------------------------------------------------

## Installation

Before you begin, ensure you have the following tools installed:

1. Git: To install Git, run:
```bash
  add-apt-repository ppa:git-core/ppa  
  apt update  
  apt-get install -y git  
```

2. Conda: The scripts will create a separate virtual environment for each release of each library and depend on Conda to manage these environments. To install Miniconda, you can run:
```bash
  MINICONDA_PATH="$HOME/miniconda"
  curl -L https://repo.anaconda.com/miniconda/Miniconda3-py310_24.5.0-0-Linux-x86_64.sh -o Anaconda_latest.sh && \
  bash ./Anaconda*.sh -b -p $CONDA_PATH ./Anaconda*.sh
  $CONDA_PATH/bin/conda install -y --only-deps anaconda && \
  $CONDA_PATH/bin/conda update -y -n base -c defaults conda && \
  $CONDA_PATH/bin/conda install -y pip
  $CONDA_PATH/bin/conda init bash
  echo 'PATH=$CONDA_PATH/bin:$PATH' >> ~/.bashrc
  source $CONDA_PATH/etc/profile.d/conda.sh
  exec bash  
```

3. Node.js & Readability: We use [readability](https://github.com/mozilla/readability) as our main tool for converting the generated HTML documentation into text. To install Node.js and Readability, run:
```bash
  curl -fsSL https://deb.nodesource.com/setup_20.x -o nodesource_setup.sh  
  sudo bash nodesource_setup.sh  
  sudo apt-get install -y nodejs  
  npm install katex jsdom @mozilla/readability  
```
Optionally, you can also use [trafilatura](https://github.com/adbar/trafilatura) instead of [readability](https://github.com/mozilla/readability) to convert HTML to text. However, we have found that Readability outperforms trafilatura in terms of accuracy and quality of extraction.

------------------------------------------------------------

## Usage

Note: The following scripts assume the user has root access to run `apt 
install` commands.

To create documentation for NumPy, modify `numpy_makefile` and set the path to 
your Conda installation, then use the following command:
```bash
  bash numpy_generate.sh <VERSION> <HTML_CONVERT_METHOD>
  # e.g., bash numpy_generate.sh 2.2.0 readability
```

Supported NumPy versions currently are:
```
np_versions = {
    "1.13.0": "06/2017",
    "1.14.0": "01/2018",
    "1.15.0": "07/2018",
    "1.16.0": "01/2019",
    "1.17.0": "07/2019",
    "1.18.0": "12/2019",
    "1.19.0": "06/2020",
    "1.20.0": "01/2021",
    "1.21.0": "06/2021",
    "1.22.0": "12/2021",
    "1.23.0": "06/2022",
    "1.24.0": "12/2022",
    "1.25.0": "06/2023",
    "1.26.0": "09/2023",
    "2.0.0": "06/2024",
    "2.1.0": "08/2024",
    "2.2.0": "12/2024",
}
```

Similarly, for PyTorch, you can use:
```bash
  bash pytorch_generate.sh <VERSION> <HTML_CONVERT_METHOD>
  # e.g., bash pytorch_generate.sh 2.4.0 readability
```

Supported PyTorch versions currently are:
```
torch_versions = {
    "1.8.0": "03/2021",
    "1.9.0": "06/2021",
    "1.10.0": "10/2021",
    "1.11.0": "03/2022",
    "1.12.0": "06/2022",
    "1.13.0": "10/2022",
    "2.0.0": "03/2023",
    "2.1.0": "10/2023",
    "2.2.0": "01/2024",
    "2.3.0": "04/2024",
    "2.4.0": "07/2024",
}
```

The final `jsonl` files for LLM Foundry evaluations will be stored in 
`./output/{numpy,pytorch}`. To run the evaluations, the data is expected to 
exist in the following paths relative to the root of the repository:
```bash
tic_codedocs_numpy_local_path="local_data/code_eval/numpy"
tic_codedocs_pytorch_local_path="local_data/code_eval/pytorch"
```

We recommend uploading them to S3 Path for future evaluations.
```bash
aws s3 cp output/numpy s3://<bucket/<prefix>/ml-tic-lm/evaluation/code_eval/numpy --recursive
aws s3 cp output/pytorch s3://<bucket/<prefix>/ml-tic-lm/evaluation/code_eval/pytorch --recursive
```

[^1]: For the experiments in our paper, we used 16 major releases of NumPy 
(from `v1.13.0` in 2017 to `v2.1.0` in 2024) and 11 major releases of PyTorch 
(from `v1.8.0` in 2021 to `v2.4.0` in 2024).

---
### Note
  
Open source libraries like NumPy/PyTorch often don't specify exact dependency versions, using formats like dependency_package or > x.y.z in their requirements files. This means pip installs different versions depending on when you run the installation, potentially breaking pipelines.
For example, [NumPy v1.19's doc requirements](https://github.com/numpy/numpy/blob/v1.19.0/doc_requirements.txt) from ~5 years ago specified:
```
sphinx>=2.2.0,<3.0
ipython
scipy
matplotlib
```
Running this in 2020 would install matplotlib 3.2, but today it would install matplotlib 3.10, which may break the document generation due to API changes.
Beyond the dependencies, development processes and tools also evolve - PyTorch, for instance, is [deprecating](https://github.com/pytorch/pytorch/issues/138506) their official conda channel.
Overall, while the scripts have been tested before the release, we note that they may stop working due to the mentioned changes.
