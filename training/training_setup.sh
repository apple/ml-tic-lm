#!/bin/bash

# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

pip install -r requirements.txt

git clone https://github.com/mlfoundations/open_lm.git
pushd open_lm
git checkout 9bb92ef1689333534b7057942a20d18a46d1fa52
git apply ../open_lm.patch
pip install -e .
popd

export AWS_MAX_ATTEMPTS=15
export AWS_RETRY_MODE="standard"
