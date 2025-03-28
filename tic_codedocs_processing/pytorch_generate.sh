#!/bin/bash

# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

clone_pytorch_if_not_exists() {
    local PYTORCH_DIR="pytorch"

    if [ ! -d "$PYTORCH_DIR" ]; then
        echo "PyTorch repository not found. Cloning into $PYTORCH_DIR..."
        if git clone https://github.com/pytorch/pytorch.git "$PYTORCH_DIR"; then
            echo "PyTorch repository cloned successfully."
            return 0
        else
            echo "Error cloning PyTorch repository."
            return 1
        fi
    else
        echo "PyTorch repository already exists in $PYTORCH_DIR. Skipping clone."
        return 0
    fi
}


checkout_pytorch_version() {
    local VERSION="$1"
    if [ -z "$VERSION" ]; then
        echo "Error: Version not provided. Usage: $0 <version>"
        return 1
    fi
    local COMMIT_HASH=$(git rev-list -n 1 "v$VERSION" 2>/dev/null)
    echo $COMMIT_HASH
    if [ -z "$COMMIT_HASH" ]; then
        echo "Error: Unable to find commit hash for version $VERSION"
        return 1
    fi
    if git checkout "$COMMIT_HASH"; then
        echo "Successfully checked out PyTorch version $VERSION"
        git submodule sync
        git submodule update --init --recursive
        return 0
    else
        echo "Error: Failed to checkout to commit $COMMIT_HASH"
        return 1
    fi
}

conda_initialized() {
    # Check if conda command is available
    if ! command -v conda &> /dev/null; then
        return 1
    fi

    # Check if conda activate works
    if ! conda activate base &> /dev/null; then
        return 1
    fi

    return 0
}


conda_install_pytorch() {
    local torch_version="$1"
    #"pt_$torch_version"
    local venv="$2"

    if ! conda_initialized; then
        echo "Conda is not initialized. Running conda init..."
        export PATH="$(conda info --base)/bin:${PATH}"
        conda init bash
    fi

    cpu_package="pytorch"
    case $torch_version in
        "1.0.0"|"1.0.1"|"1.1.0" | "1.9.0")
            python_version="3.6.8"
            cpu_package="pytorch-cpu"
            ;;
        "1."*)
            python_version="3.8.6"
            ;;
        "2."*)
            python_version="3.10.8"
            ;;
        *)
            echo "Unsupported PyTorch version."
            exit 1
            ;;
    esac
    echo "Going to install $torch_version with python=${python_version}"
    conda create -n $venv python=$python_version -y  --no-default-packages
    source $(conda info --base)/etc/profile.d/conda.sh
    conda activate $venv
    pip install packaging
    pip install "numpy<2.0"

    conda install ${cpu_package}==$torch_version torchvision cpuonly -c pytorch -y
    echo "PyTorch $torch_version has been installed in the '$venv' environment"
}

install_pytorch_from_source() {
    local VERSION="$1"
    local venv="$2"
    echo "Activating virtual environment: $venv"
    pyenv activate "$venv"

    pip install cmake ninja
    pip install -r requirements.txt
    pip install packaging
    pip install "numpy<2.0"

    export USE_CUDA=0
    export USE_CUDNN=0
    export USE_MKLDNN=1
    export MAX_JOBS=8
    if python setup.py install; then
        echo "PyTorch $VERSION (CPU only) installed successfully in $venv"
    else
        echo "Error: Failed to build and install PyTorch"
        pyenv deactivate
        return 1
    fi
}

process_file() {
    node ../html2text.js "$1"
}
export -f process_file

html2text() {
    local directory="$1"
    local venv="$2"
    local method="$3"


    # Check if the directory exists
    if [ ! -d "$directory" ]; then
        echo "Error: Directory '$directory' does not exist."
        return 1
    fi

    echo "converting html docs to text via ${method}"
    case "$method" in
        readability)
            find "$directory" -type f -name "*.html" -print0 | xargs -0 -P 16 -I {} node convert_readability.js "{}"
            ;;
        trafilatura)
            $(conda info --base)/envs/${venv}/bin/pip install -U trafilatura
            find "$directory" -type f -name "*.html" -print0 | xargs -0 -P 16 -I {} $(conda info --base)/envs/${venv}/bin/python convert_trafilatura.py "{}"
            ;;
        *)
            echo "Invalid method: $method"
            echo "Supported methods: readability and trafilatura"
            return 1
            ;;
    esac

}

pytorch_bulild_docs() {
    local venv=$1
    cd docs
    $(conda info --base)/envs/${venv}/bin/pip install packaging fsspec
    $(conda info --base)/envs/${venv}/bin/pip install "numpy<2.0"
    $(conda info --base)/envs/${venv}/bin/pip install -r requirements.txt
    $(conda info --base)/envs/${venv}/bin/pip install "Jinja2<3.1"
    make clean
    make html
    cd ..
}


check_arguments() {
    if [ $# -ne 2 ]; then
        echo "Usage: $0 <VERSION> <HTML_CONVERT_METHOD>"
        echo "supported methods: trafilatura and readability"
        exit 1
    fi
}

VERSION="$1"
VENV_NAME="pt_$1"
METHOD="$2"
check_arguments $1 $2
echo $1 $2
clone_pytorch_if_not_exists
cd pytorch
checkout_pytorch_version $VERSION
conda_install_pytorch $VERSION $VENV_NAME
pytorch_bulild_docs $VENV_NAME
cd ..
html2text "pytorch/docs/build/html/" $VENV_NAME $METHOD
mkdir -p "./output"
cp -r "pytorch/docs/build/html/" "./output/torch_${VERSION}_${METHOD}"
$(conda info --base)/envs/${VENV_NAME}/bin/python pytorch_process.py $VERSION $METHOD

