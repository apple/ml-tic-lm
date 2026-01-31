# TiC-LM

This software project accompanies the following research paper:

[TiC-LM: A Web-Scale Benchmark for Time-Continual LLM Pretraining, Li, J., Armandpour, M., Mirzadeh, I., Mehta, S., Shankar, V., Vemulapalli, R., Bengio, S., Tuzel, O., Farajtabar, M., Pouransari H., and Faghri, F., ArXiv preprint, 2025.](https://arxiv.org/abs/2504.02107)

## Overview

We provide a high-level overview of the structure and main components (i.e., dataset creation, training, evaluation) of this codebase:
- [`models`](models/) contains instructions for downloading the Oracle models and their evaluation metrics.
- [`tic_cc_processing`](tic_cc_processing/) contains the code for generating both the TiC-CC trianing dataset and heldout evaluation sets
- [`tic_wiki_processing`](tic_wiki_processing/), [`tic_stackexchange_processing`](tic_stackexchange_proecssing/), and [`tic_codedocs_processing`](tic_codedocs_processing/) each contain the code for generating the TiC-Wiki, TiC-Stackexchange, and TiC-CodeDocs evaluations respectively
- [`training`](training/) contains code for running the various continual learning methods that we benchmark in our paper
- [`evaluation`](evaluation/) contains code for running evaluations

Each of these folders contains its own instructions for setting up environments and how to use their code. We defer more specific details about each to their specific READMEs.

## Note on Data

This benchmark provides scripts for reproducing the training/evaluation data from publicly available sources. It does not redistribute any original data. All data accessed for the creation of these scripts was obtained prior to August 2024. The data sourced from Wikipedia, StackExchange, and code repositories, is used solely for the purpose of benchmark construction and evaluation, and is not used for training any models. Users are responsible for adhering to the terms of service and licensing agreements of the respective data sources. Please be aware that data from public sources can change over time, which may affect the reproducibility of this benchmark. We recommend reporting standard deviations for multiple training and evaluations. The scripts provided in this benchmark are released under the [ASCL license](./LICENSE).

## Acknowledgements
Our codebase is built using multiple open source contributions, please see [ACKNOWLEDGEMENTS](ACKNOWLEDGEMENTS) for more details. 

## License

This software and accompanying data and models have been released under the 
following licenses:
- Code: [Apple Sample Code License (ASCL)](./LICENSE)
- ML models: [Apple ML Research Model TOU](./LICENSE_MODELS)
- Data: [CC-BY-NC-ND](./LICENSE_DATA) [Deed](https://creativecommons.org/licenses/by-nc-nd/4.0/)

## Citation

If you find this repository useful or use this code in your research, please cite the following paper:

TiC-LM: A Web-Scale Benchmark for Time-Continual LLM Pretraining, Li, J., Armandpour, M., Mirzadeh, I., Mehta, S., Shankar, V., Vemulapalli, R., Bengio, S., Tuzel, O., Farajtabar, M., Pouransari H., and Faghri, F., ArXiv preprint, 2025.

```
@article{li2025ticlm,
  title={TiC-LM: A Web-Scale Benchmark for Time-Continual LLM Pretraining},
  author={Li, Jeffrey and Armandpour, Mohammadreza and Mirzadeh, Iman and Mehta, Sachin and Shankar, Vaishaal and Vemulapalli Raviteja and Bengio, Samy and Tuzel, Oncel and Farajtabar, Mehrdad and Pouransari, Hadi and Faghri, Fartash},
  journal={arXiv preprint arXiv:2504.02107},
  year={2025}
}
```
