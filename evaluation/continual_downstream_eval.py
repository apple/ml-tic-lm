# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
# 

import argparse
import builtins as __builtin__
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytz
import torch
from utils import update_args_from_openlm_config
from composer.loggers import InMemoryLogger, LoggerDestination
from composer.trainer import Trainer
from composer.utils import dist, get_device, reproducibility
from llmfoundry.utils.builders import build_icl_evaluators, build_logger
from omegaconf import OmegaConf as om
from open_lm.attention import ATTN_ACTIVATIONS, ATTN_SEQ_SCALARS
from open_lm.distributed import init_distributed_device, world_info_from_env
from open_lm.model import create_params
from open_lm.main import load_model
from open_lm.file_utils import pt_load
from llm_foundry_wrapper import SimpleComposerOpenLMCausalLM
from open_lm.utils.transformers.hf_config import OpenLMConfig
from open_lm.utils.transformers.hf_model import OpenLMforCausalLM
from pytz import timezone
from transformers import AutoModelForCausalLM, AutoTokenizer, GPTNeoXTokenizerFast, LlamaTokenizerFast

builtin_print = __builtin__.print


def setup_for_distributed(is_master):
    def print(*args, **kwargs):
        force = kwargs.pop("force", False)
        if is_master or force:
            builtin_print(*args, **kwargs)

    __builtin__.print = print


@torch.no_grad()
def evaluate(model, tokenizer, cfg, force_download=False):
    cfg.dist_timeout = cfg.get("dist_timeout", 600.0)
    reproducibility.seed_all(cfg.seed)
    dist.initialize_dist(get_device(None), timeout=cfg.dist_timeout)
    setup_for_distributed(dist.get_global_rank() == 0)

    icl_tasks_w_categories = list(
        filter(lambda x: 0 if "has_categories" not in x else x["has_categories"], cfg.icl_tasks)
    )
    icl_tasks_w_categories = list(map(lambda x: x["label"], icl_tasks_w_categories))

    evaluators, logger_keys = build_icl_evaluators(
        cfg.icl_tasks, tokenizer, cfg.max_seq_len, cfg.device_eval_batch_size
    )
    in_memory_logger = InMemoryLogger()  # track metrics in the in_memory_logger
    loggers: List[LoggerDestination] = [
        build_logger(name, logger_cfg) for name, logger_cfg in (cfg.get("loggers") or {}).items()
    ]
    loggers.append(in_memory_logger)

    fsdp_config = None
    fsdp_config = om.to_container(fsdp_config, resolve=True) if fsdp_config is not None else None

    load_path = cfg.get("load_path", None)

    composer_model = SimpleComposerOpenLMCausalLM(model, tokenizer)

    trainer = Trainer(
        model=composer_model,
        loggers=loggers,
        precision=cfg.precision,
        fsdp_config=fsdp_config,
        load_path=load_path,
        load_weights_only=True,
        progress_bar=False,
        log_to_console=True,
        dist_timeout=cfg.dist_timeout,
    )

    if torch.cuda.is_available():
        torch.cuda.synchronize()
    a = time.time()
    trainer.eval(eval_dataloader=evaluators)
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    b = time.time()

    print(f"Ran eval in: {b-a} seconds")
    performance_on_tasks = defaultdict(list)
    for key in logger_keys:
        if key in in_memory_logger.data:
            result = in_memory_logger.data[key][0][1].item()
            flag = True
            if len(icl_tasks_w_categories) > 0:
                for task in icl_tasks_w_categories:
                    if task in key:
                        performance_on_tasks[task].append(result)
                        flag = False
            if flag:
                performance_on_tasks[key].append(result)

    report_results = {}
    for task in performance_on_tasks:
        result = sum(performance_on_tasks[task]) / len(performance_on_tasks[task])
        if len(task.split("/")) > 1:
            label = task.split("/")[1]
            report_results[label] = result
        else:
            report_results[task] = result
    print(report_results)

    # Deals with case where there are multiple metrics per task
    has_multiple_metrics = False
    multi_metric_results = {}
    for key in logger_keys:
        task = key.split('/')[1]
        metric = key.split('/')[-1]
        if task not in multi_metric_results:
            multi_metric_results[task] = {}
        if metric not in multi_metric_results[task]:
            multi_metric_results[task][metric] = in_memory_logger.data[key][0][1].item()
            if len(multi_metric_results[task]) > 1:
                has_multiple_metrics = True

    if has_multiple_metrics:
        print("Multiple metrics detected. Here's the detailed breakdown:")
        print(json.dumps(multi_metric_results, indent=2))

    for task, metrics in multi_metric_results.items():
        old_label = task
        if len(metrics) > 1:
            for m,v in metrics.items():
                new_label = "_".join([old_label, m])
                report_results[new_label] = v

            del report_results[old_label]

    print(report_results)
    return report_results


def set_args_for_val(args, data, key):
    setattr(args, "val_data", data)
    setattr(args, "val_data_key", key)
    setattr(args, "squash_mask_left", True)
    setattr(args, "target_mask_individual", 50400)
    setattr(args, "target_mask_left", 50300)
    setattr(args, "val_seq_ci", True)
    setattr(args, "val_tok_ci", True)
    return args


def main():
    parser = argparse.ArgumentParser()

    # Arguments that openlm requires when we call load_model
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed for reproducibility, when None, will use the seed from the eval config file.",
    )
    parser.add_argument("--fsdp", default=False, action="store_true")
    parser.add_argument("--distributed", default=True, action="store_true")
    parser.add_argument("--resume", default=None, type=str)

    # Argument for uploading results
    parser.add_argument("--remote-sync", type=str, default=None)
    parser.add_argument("--remote-sync-protocol", type=str, default="s3", choices=["s3", "fsspec"])
    parser.add_argument("--checkpoint", default=None, type=str, help="Path to checkpoint to evaluate.")
    parser.add_argument("--eval-yaml", type=str, default="light.yaml")
    parser.add_argument("--tokenizer", type=str, default="EleutherAI/gpt-neox-20b")
    parser.add_argument("--config", default=None, type=str)
    parser.add_argument("--model", default=None, type=str)
    parser.add_argument("--hf-model", default=None)
    parser.add_argument("--hf-cache-dir", default=None)
    parser.add_argument("--output-file", type=str, default=None)
    parser.add_argument("--time-range", type=str, help="Time range for the evaluation")
    parser.add_argument(
        "--use-temp-working-dir",
        action="store_true",
        help="Use a temporary working directory for the evaluation. removing it when done. "
        "This is required if you wish to run multiple evaluations with the same datasets"
        " in parallel on the same node.",
    )
    parser.add_argument(
        "--eval_meta_data", default=f"{os.path.dirname(__file__)}/eval_meta_data.csv", help="Eval meta data file"
    )
    parser.add_argument(
        "--preset-world-size",
        type=int,
        default=None,
        help="Explicitly set the world size. Useful in cases where a different number of gpus per node need to be used.",
    )
    parser.add_argument(
        "--attn-name",
        type=str,
        default="xformers_attn",
        choices=["xformers_attn", "torch_attn", "custom_attn"],
        help="type of attention to use",
    )
    parser.add_argument(
        "--attn-activation",
        type=str,
        default=None,
        choices=list(ATTN_ACTIVATIONS.keys()),
        help="activation to use with custom_attn",
    )
    parser.add_argument(
        "--attn-seq-scalar",
        type=str,
        default=None,
        choices=list(ATTN_SEQ_SCALARS.keys()),
        help="different ways to set L, where L^alpha divides attention logits post activation",
    )
    parser.add_argument(
        "--attn-seq-scalar-alpha",
        type=float,
        default=None,
        help="power alpha to raise L to, where L^alpha divides attention logits post activation",
    )
    parser.add_argument("--force-eval-download", action='store_true', help="Forces re-download of the eval data.")
    parser.add_argument("--averager-name", help="If specified, load this averager from checkpoint.")
    parser.add_argument("--force-xformers", action="store_true")

    args = parser.parse_args()
    orig_seed = args.seed  # may be overridden by config file if it exists

    if args.config is not None:
        assert args.hf_model is None, (
            "If you are using a config file, "
            "you are trying to evaluate open_lm model. Please remove hf-model argument."
        )
        update_args_from_openlm_config(args)
        # disable wandb for eval
        args.wandb = None
    else:
        # Most probably evaling a hf-model.
        assert args.hf_model, (
            "If you are not using a config file, you might want to evaluate a Hugginface model, "
            "so please provide hf-model argument."
        )

        # Setting these params as they are needed to run distributed evals
        # and they are supposed to come from config file.
        args.dist_backend = "nccl"
        args.dist_url = "env://"
        args.no_set_device_rank = False
        args.model = args.hf_model
        args.force_distributed = False

    with open(args.eval_yaml) as f:
        eval_cfg = om.load(f)

    if orig_seed is not None:
        print(f"Overriding eval config seed ({eval_cfg.seed}) to {orig_seed}")
        eval_cfg.seed = orig_seed

        # now need to set the 'fewshot_random_seed' in each config in the icl task configs
        for icl_cfg in eval_cfg.icl_tasks:
            icl_cfg.fewshot_random_seed = orig_seed

    args.resume = args.checkpoint
    args.remote_sync = args.output_file
    directory = os.path.dirname(args.output_file)
    if directory != "" and not os.path.exists(directory):
        os.makedirs(directory)

    CWD = os.getcwd()
    if args.use_temp_working_dir:
        temp_dir = os.path.join(CWD, "eval_openlm_ckpt_temp_dirs", f"{uuid.uuid4()}")
        os.makedirs(temp_dir, exist_ok=True)  # in case rank > 0
        os.chdir(temp_dir)
        print(f"Using temporary working directory: {temp_dir}")

    print("Loading model into the right classes")
    if args.hf_model is not None:
        eval_model = AutoModelForCausalLM.from_pretrained(
            args.hf_model, trust_remote_code=True, cache_dir=args.hf_cache_dir
        )
    else:
        params = create_params(args)
        eval_model = OpenLMforCausalLM(OpenLMConfig(params))

    if "gpt-neox-20b" in args.tokenizer:
        tokenizer = GPTNeoXTokenizerFast.from_pretrained("EleutherAI/gpt-neox-20b")
    elif "llama" in args.tokenizer:
        tokenizer = LlamaTokenizerFast.from_pretrained(args.tokenizer)
        if len(tokenizer) > eval_model.config.vocab_size:  # happens in llama-3-8b
            print(f"Resizing vocab from {eval_model.config.vocab_size} to {len(tokenizer)}")
            eval_model.resize_token_embeddings(len(tokenizer))
    else:
        tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, trust_remote_code=True, cache_dir=args.hf_cache_dir)

    if args.checkpoint is not None:
        if not args.averager_name:
            print(f"Loading checkpoint {args.checkpoint}")
            args.distributed = False
            load_model(args, eval_model.model, different_seed=True)
            args.distributed = True
        else:
            print(f"Loading checkpoint {args.checkpoint}")
            checkpoint = pt_load(args.resume, map_location="cpu")
            if "epoch" in checkpoint:
                # resuming a train checkpoint w/ epoch and optimizer state
                start_epoch = checkpoint["epoch"]
                avg_sd = torch.load(args.checkpoint, map_location="cpu")
                if next(iter(avg_sd.items()))[0].startswith("module"):
                    avg_sd = {k[len("module.") :]: v for k, v in avg_sd.items()}
                eval_model.model.load_state_dict(avg_sd)

        # HF model loaded with from_pretrained is by default in eval mode.
        # https://github.com/huggingface/transformers/blob/ebfdb9ca62205279d5019ef1403877461b3b2da4/src/transformers/modeling_utils.py#L2500
        eval_model.model.eval()

    # Set requires grad = False to reduce memory consumption - o/w composer makes a copy of the model.
    for p in eval_model.parameters():
        p.requires_grad = False

    device = init_distributed_device(args)
    eval_model = eval_model.to(device)
    eval_metrics = {}
    local_rank, _, _ = world_info_from_env()

    icl_results = evaluate(eval_model, tokenizer, eval_cfg, force_download=args.force_eval_download)
    eval_metrics["icl"] = icl_results

    date_format = "%Y_%m_%d-%H_%M_%S"
    date = datetime.now(tz=pytz.utc)
    date = date.astimezone(timezone("US/Pacific"))
    date = date.strftime(date_format)

    output = {
        "name": str(args.eval_yaml)[:-5],
        "uuid": str(uuid.uuid4()),
        "model": args.model,
        "creation_date": date,
        "eval_metrics": eval_metrics,
    }

    print("Eval output: ")
    print(json.dumps(output, indent=4, sort_keys=True))
    if local_rank == 0:
        if args.use_temp_working_dir:
            print(f"Removing temporary working directory: {temp_dir} amd changing back to {CWD}")
            shutil.rmtree(temp_dir)
            os.chdir(CWD)  # need to change back BEFORE we save the output file

        with open(args.output_file, "w") as f:
            json.dump(output, f, indent=4)

    return output


if __name__ == "__main__":
    main()
