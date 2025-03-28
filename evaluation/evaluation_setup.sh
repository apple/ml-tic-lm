#!/bin/bash

# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#


# Encompasses the open_lm requirements
pip install -r requirements.txt

git clone https://github.com/mlfoundations/open_lm.git
pushd open_lm
git checkout 9bb92ef1689333534b7057942a20d18a46d1fa52
git apply ../../training/open_lm.patch
pip install -e .
popd

# Run static download script
./download_static_evals.sh

pip install --user -U nltk
python -m nltk.downloader all
