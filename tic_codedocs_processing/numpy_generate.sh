#!/bin/bash

# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

NUM_THREADS=$(nproc --all)

if [ -z "${CONDA_ROOT}" ]; then
    CONDA_ROOT=$(conda info --base)
    echo "CONDA_ROOT not provided, using default: ${CONDA_ROOT}"
else
    echo "Using provided CONDA_ROOT: ${CONDA_ROOT}"
fi

clone_if_not_exists() {
    local DIR="numpy"

    if [ ! -d "$DIR" ]; then
        echo "repository not found. Cloning into $DIR..."
        if git clone https://github.com/numpy/numpy.git "$DIR"; then
            echo "repository cloned successfully."
            return 0
        else
            echo "Error cloning repository."
            return 1
        fi
    else
        echo "$DIR repository already exists in $DIR. Skipping clone."
        return 0
    fi
}


checkout_version() {
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
        echo "Successfully checked out version $VERSION"
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


conda_install_numpy() {
    local np_version="$1"
    local venv="$2"

    if ! conda_initialized; then
        echo "Conda is not initialized. Running conda init..."
        export PATH="${CONDA_ROOT}/bin:${PATH}"
        conda init bash
    fi

    local py_ver="3.8.4"
    IFS='.' read -r -a version_parts <<< "$np_version"
    major=${version_parts[0]}
    minor=${version_parts[1]}
    patch=${version_parts[2]}

    apt install -y graphviz texlive-fonts-recommended texlive-latex-recommended texlive-latex-extra latexmk texlive-xetex
    # Determine the appropriate Python version
    if [[ $major -eq 1 && $minor -ge 25 ]]; then
        py_ver="3.9"
    elif [[ $major -eq 1 && $minor -ge 20 && $minor -le 24 ]]; then
        py_ver="3.8.4"
    elif [[ $major -eq 2 || $major -gt 2 ]]; then
        py_ver="3.10.1"
    elif [[ $major -eq 1 && $minor -lt 20 ]]; then
        py_ver="3.6.6"
    elif [[ $major -eq 1 && $minor -lt 16 ]]; then
        py_ver="3.4.1"
    else
        echo "Unsupported numpy version: $np_version"
        return 1
    fi
    if [[ $major -eq 1 && $minor -eq 25 || $minor -eq 26  ]]; then
        conda env create -n $venv -f environment.yml -y --no-default-packages
    elif [[ $major -eq 1 && $minor -lt 25 ]]; then
        echo "Going to install $np_version with python=${py_ver}"
        conda create -n $venv python=$py_ver -y --channel=conda-forge --no-default-packages
    elif [[ $major -eq 2 ]]; then
        conda create -n $venv python=$py_ver -y --channel=conda-forge --no-default-packages
    fi
    source ${CONDA_ROOT}/etc/profile.d/conda.sh
    eval "$(conda shell.bash hook)"
    conda activate $venv
    export MAKEFLAGS="-j${NUM_THREADS}"
    # why all these ifs?
    # because there is no max-version-pinning in numpy
    # i.e., if you hav "dependency > 1.0" in requirements.txt,
    # and you run this code in 2020, it probably mean v1.1 or v2.0
    # but in 2025, it might mean v5.0 and this could break things
    if [[ $major -eq 2 ]]; then
        ${CONDA_ROOT}/envs/${venv}/bin/pip install -r "./requirements/build_requirements.txt"
        BLAS=None LAPACK=None ATLAS=None ${CONDA_ROOT}/envs/${venv}/bin/pip install . --no-build-isolation

    elif [[ $major -eq 1 && $minor -eq 26 ]]; then
        ${CONDA_ROOT}/envs/${venv}/bin/pip install scipy pandas
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Cython==3.0.2"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "mypy==1.5.1"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "charset-normalizer==3.2.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "typing_extensions==4.6.3"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "meson==1.2.1"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install --upgrade pip 'setuptools==68.1.2'
        BLAS=None LAPACK=None ATLAS=None ${CONDA_ROOT}/envs/${venv}/bin/python setup.py build_ext --cpu-baseline="native" --cpu-dispatch="none" bdist
    elif [[ $major -eq 1 && $minor -eq 25 ]]; then
        ${CONDA_ROOT}/envs/${venv}/bin/pip install scipy pandas
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Cython==0.29.35"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "mypy==0.981"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "typing_extensions==4.6.3"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install --upgrade pip 'setuptools==67.8.0'
    elif [[ $major -eq 1 && $minor -eq 24 ]]; then
        ${CONDA_ROOT}/envs/${venv}/bin/pip install scipy pandas
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Cython==0.29.30"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "mypy==0.950"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "typing_extensions==4.3.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install --upgrade pip 'setuptools==65.6.2'
    elif [[ $major -eq 1 && $minor -eq 22 || $minor -eq 23 ]]; then
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Pillow<9.0.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "scipy==1.6.1"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "pandas==1.2.3"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Cython==0.29.24"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "mypy==0.930"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "typing_extensions==3.7.4.1"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install --upgrade pip 'setuptools==59.2.0'
    elif [[ $major -eq 1 && $minor -ge 20 && $minor -le 21 ]]; then
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "matplotlib==3.3.4"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Pillow<=8.0.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "scipy==1.5.4"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "pickle5==0.0.11"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Cython==0.29.21"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "mypy==0.790"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "typing_extensions==3.7.4.1"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "pandas==1.1.5"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install --upgrade pip 'setuptools==51.1.1'
        ${CONDA_ROOT}/envs/${venv}/bin/pip uninstall numpy -y
        BLAS=None LAPACK=None ATLAS=None ${CONDA_ROOT}/envs/${venv}/bin/python setup.py develop
    elif [[ $major -eq 1 && $minor -eq 19 ]]; then
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Cython==0.29.17"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "scipy==1.4.1"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "pandas==1.0.4"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "matplotlib==2.2.5"
        ${CONDA_ROOT}/envs/${venv}/bin/pip uninstall numpy -y
        BLAS=None LAPACK=None ATLAS=None ${CONDA_ROOT}/envs/${venv}/bin/python setup.py develop
    elif [[ $major -eq 1 && $minor -eq 18 ]]; then
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "scipy==1.3.3"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Cython==0.29.16,<3.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "matplotlib==2.2.3"
        # BLAS=None LAPACK=None ATLAS=None ${CONDA_ROOT}/envs/${venv}/bin/python setup.py build_ext --inplace -j 8 --fcompiler=gnu95
        ${CONDA_ROOT}/envs/${venv}/bin/pip uninstall numpy -y
        BLAS=None LAPACK=None ATLAS=None ${CONDA_ROOT}/envs/${venv}/bin/python setup.py develop
    elif [[ $major -eq 1 && $minor -eq 17 ]]; then
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Cython==0.29.12"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "scipy==1.3.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install -e .
    elif [[ $major -eq 1 && $minor -lt 17 ]]; then
        ${CONDA_ROOT}/envs/${venv}/bin/pip install cython scipy
        ${CONDA_ROOT}/envs/${venv}/bin/pip install -e .
    fi
}


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
            find "$directory" -type f -name "*.html" -print0 | xargs -0 -P ${NUM_THREADS} -I {} node convert_readability.js "{}"
            ;;
        trafilatura)
            ${CONDA_ROOT}/envs/${venv}/bin/pip install -U trafilatura
            find "$directory" -type f -name "*.html" -print0 | xargs -0 -P ${NUM_THREADS} -I {} ${CONDA_ROOT}/envs/${venv}/bin/python convert_trafilatura.py "{}"
            ;;
        *)
            echo "Invalid method: $method"
            echo "Supported methods: readability and trafilatura"
            return 1
            ;;
    esac

}

build_docs_numpy() {
    local np_version=$1
    local venv=$2
    apt update -y
    apt install -y doxygen gcc g++ gfortran libopenblas-dev liblapack-dev pkg-config

    IFS='.' read -r -a version_parts <<< "$np_version"
    major=${version_parts[0]}
    minor=${version_parts[1]}
    patch=${version_parts[2]}

    # Determine the appropriate Python version
    if [[ $major -eq 1 && $minor -eq 26 ]]; then
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "sphinx==7.1.2"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Jinja2<3.1"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Pygments==2.12.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "numpydoc==1.4.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "pydata-sphinx-theme==0.13.3"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "ipython<8.8"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "sphinx-design==0.5.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "breathe==4.35.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "towncrier==22.12.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "toml"
        cd doc
    elif [[ $major -eq 1 && $minor -eq 25 ]]; then
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "sphinx==6.2.1"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Jinja2<3.1"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Pygments==2.12.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "numpydoc==1.4.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "pydata-sphinx-theme==0.13.3"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "ipython<8.8"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "sphinx-design==0.3.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "breathe==4.34.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "towncrier==22.12.0"
        cd doc
    elif [[ $major -eq 1 && $minor -eq 24 ]]; then
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "sphinx==5.3.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Jinja2<3.1"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Pygments==2.12.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "numpydoc==1.3.1"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "pydata-sphinx-theme==0.12.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "ipython<8.8"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "sphinx-design==0.3.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "breathe==4.34.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "towncrier==22.12.0"
        cd doc
    elif [[ $major -eq 1 && $minor -eq 23 ]]; then
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "sphinx==4.5.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Jinja2<3.1"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Pygments==2.12.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "numpydoc==1.3.1"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "pydata-sphinx-theme==0.8.1"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "ipython<8.8"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "sphinx-panels"
        cd doc
    elif [[ $major -eq 1 && $minor -eq 22 ]]; then
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "sphinx==4.3.1"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Jinja2<3.1"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Pygments==2.9.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "numpydoc==1.2.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "pydata-sphinx-theme==0.7.2"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "ipython<8.8"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "sphinx-panels"
        cd doc
    elif [[ $major -eq 1 && $minor -eq 21 ]]; then
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "sphinx==4.0.1"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Jinja2<3.1"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Pygments==2.9.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "numpydoc==1.2.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "pydata-sphinx-theme==0.5.2"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "ipython<8.8"
        cd doc
    elif [[ $major -eq 1 && $minor -eq 20 ]]; then
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "sphinx==2.4.4"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Pygments==2.7.3"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Jinja2<3.1"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "numpydoc==1.2.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "pydata-sphinx-theme==0.4.1"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "ipython<8.8"
        cd doc
    elif [[ $major -eq 1 && $minor -eq 19 ]]; then
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Pygments==2.6.1"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Jinja2<3.1"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "ipython<8.8"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install -r ./doc_requirements.txt
        cd doc
    elif [[ $major -eq 2 || $major -gt 2 ]]; then
        ${CONDA_ROOT}/envs/${venv}/bin/pip install -r requirements/doc_requirements.txt
        cd doc
    elif [[ $major -eq 1 && $minor -eq 18 ]]; then
        cd doc
        cd sphinxext
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "charset-normalizer==2.0.12"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install -U "sphinx==2.2.0"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Jinja2<3.1"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "ipython<8.8"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Pygments==2.5.2"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install -e .
        cd ..
    elif [[ $major -eq 1 && $minor -lt 18 ]]; then
        cd doc
        cd sphinxext
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "charset-normalizer==2.0.12"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "sphinx<1.7"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install --force-reinstall "alabaster==0.7.10"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "Jinja2==2.9.6"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "ipython<8.8"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "matplotlib==2.0.2"
        ${CONDA_ROOT}/envs/${venv}/bin/pip install "markupsafe==2.0.1"

        ${CONDA_ROOT}/envs/${venv}/bin/pip install -e .
        cd ..
    else
        echo "Unsupported numpy version: $np_version -> $major $minor $patch"
        return 1
    fi

    eval "$(conda shell.bash hook)"
    conda activate $venv
    rm Makefile
    touch preprocess.py
    cp ../../numpy_makefile ./Makefile
    make clean
    CONDA_ROOT=${CONDA_ROOT} VENV=${venv} NUM_THREADS=${NUM_THREADS} make html
    git stash
    cd ..
}


check_arguments() {
    if [ $# -ne 2 ]; then
        echo "Usage: $0 <VERSION> <HTML_CONVERT_METHOD>"
        echo "supported methods: trafilatura and readability"
        exit 1
    fi
}

verify_np_ver() {
    # Check if numpy is installed and get its version
    local venv=$2
    numpy_version=$(${CONDA_ROOT}/envs/${venv}/bin/python -c "import numpy; print(numpy.__version__)" 2>/dev/null)


    if [ $? -ne 0 ]; then
        echo "NumPy is not installed. Please install NumPy and try again."
        exit 1
    fi

    # Compare the installed version with the required version
    if [ "$numpy_version" = $1 ]; then
        echo "NumPy version is correct"
    else
        echo "NumPy version is incorrect. Found $numpy_version, but $1 is required."
        exit 1
    fi
}

VERSION="$1"
VENV_NAME="np_$1"
METHOD="$2"
check_arguments $1 $2
echo $1 $2
clone_if_not_exists
cd numpy
checkout_version $VERSION
conda_install_numpy $VERSION $VENV_NAME
echo "done installing numpy"
# verify_np_ver $VERSION $VENV_NAME
build_docs_numpy $VERSION $VENV_NAME
echo "done building docs"
cd ..
echo "built the html docs, going to convert to text"
html2text "numpy/doc/build/html/" $VENV_NAME $METHOD
mkdir -p "./output/numpy"
cp -r "numpy/doc/build/html/" "./output/numpy/v${VERSION}_${METHOD}"
${CONDA_ROOT}/envs/${VENV_NAME}/bin/python numpy_process.py $VERSION $METHOD
rm -rf "./output/numpy/v${VERSION}_${METHOD}"
