#!/bin/bash
# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
# 

curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs > rustup.sh
bash rustup.sh -y
source ~/.bashrc

# Clone DCLM and retrieve just the tokshuf-rs directory
git clone https://github.com/mlfoundations/dclm.git
cp -r dclm/rust_processing/tokshuf-rs/ tokshuf-rs
rm -rf dclm

# Build the tokshuf-rs binary
cd tokshuf-rs && cargo build --release
