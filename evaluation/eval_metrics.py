# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
# 

import torch
from torch import Tensor
import torch.nn as nn
import nltk
from torchmetrics import Metric
from typing import Mapping, Union
import torch.nn.functional as F
from torchmetrics import Metric
import copy



import torch
import torch.nn.functional as F
from torchmetrics import Metric
from typing import Dict, Any, Callable
import functools

class InContextLearningMetric(Metric):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.needs_batch = True

    def _wrap_update(self, update: Callable) -> Callable:
        """Overwrite default _wrap_update to return result of update()."""
        @functools.wraps(update)
        def wrapped_func(*args: Any, **kwargs: Any) -> Any:
            self._computed = None
            self._update_count += 1
            with torch.set_grad_enabled(self._enable_grad):
                try:
                    update_result = update(*args, **kwargs)
                except RuntimeError as err:
                    if 'Expected all tensors to be on' in str(err):
                        raise RuntimeError(
                            'Encountered different devices in metric calculation (see stacktrace for details). ' +
                            'This could be due to the metric class not being on the same device as input. ' +
                            f'Instead of `metric={self.__class__.__name__}(...)` try to do ' +
                            f'`metric={self.__class__.__name__}(...).to(device)` where ' +
                            'device corresponds to the device of the input.'
                        ) from err
                    raise err

            if self.compute_on_cpu:
                self._move_list_states_to_cpu()
            return update_result

        return wrapped_func

    def update(
        self,
        batch: Dict[str, Any],
        outputs: torch.Tensor,
        labels: torch.Tensor,
    ) -> Dict[str, Any]:
        """Abstract interface for computing in-context learning metrics."""
        raise NotImplementedError


class InContextLearningGoldPerplexityMetric(InContextLearningMetric):
    """Computes average perplexity for gold choices in In-context learning multiple choice tasks.

    This metric calculates the perplexity only for the gold (correct) choice in each group of choices
    and returns the average across all instances.

    Adds metric state variables:
        total_perplexity (float): The sum of perplexities for gold choices.
        total (float): The number of total instances that were evaluated.

    Args:
        dist_sync_on_step (bool, optional): Synchronize metric state across processes at
            each forward() before returning the value at the step. Default: ``False``.
    """

    def __init__(self, dist_sync_on_step: bool = False):
        super().__init__(dist_sync_on_step=dist_sync_on_step)
        self.add_state('total_perplexity', default=torch.tensor(0.0), dist_reduce_fx='sum')
        self.add_state('total', default=torch.tensor(0.0), dist_reduce_fx='sum')

        self.metric_result_dict = {
            'context': [],
            'gold_choice': [],
            'gold_perplexity': [],
        }

    def update(self, batch: Dict[str, Any], outputs: torch.Tensor, labels: torch.Tensor) -> Dict[str, Any]:
        perplexities = []
        for batch_idx, cont_idx in enumerate(batch['continuation_indices']):
            # continuation indices refer to indices in the original input's token space
            cont_tok_logits = outputs[batch_idx].index_select(
                dim=0,
                index=cont_idx - 1,
            )
            # labels have been shifted left by one index, so the cont_idx needs to be shifted as well.
            cont_tok_targ = labels[batch_idx].index_select(
                dim=0,
                index=cont_idx - 1,
            )
            cross_entropy = F.cross_entropy(cont_tok_logits, cont_tok_targ)
            perplexity = torch.exp(cross_entropy)
            perplexities.append(perplexity)

        metric_result_dict = copy.deepcopy(self.metric_result_dict)
        for (start, end), gold_idx in zip(
            batch['choice_groupings'],
            batch['gold_indices'],
        ):
            subset = perplexities[start:end]
            gold_perplexity = subset[gold_idx]

            self.total_perplexity += gold_perplexity
            self.total += 1

            question = batch['input_ids'][start][:batch['continuation_indices'][start][0]]
            gold_choice = batch['input_ids'][start + gold_idx][
                batch['continuation_indices'][start + gold_idx][0]:
                batch['continuation_indices'][start + gold_idx][-1] + 1
            ]

            metric_result_dict['context'].append(question)
            metric_result_dict['gold_choice'].append(gold_choice)
            metric_result_dict['gold_perplexity'].append(gold_perplexity.item())

        return metric_result_dict

    def compute(self):
        return self.total_perplexity.float() / self.total



class PerplexityIgnoringPad(Metric):
    """
    A Torchmetric class that computes cross entropy and perplexity for language modeling outputs,
    ignoring specified indices (e.g., padding or other special tokens).
    Args:
        dist_sync_on_step (bool, optional): Synchronize metric state across processes at
            each forward() before returning the value at the step. Default: ``False``.
        ignore_index (int, optional): The class index to ignore (e.g., for padding tokens). Default: ``-100``.
        pad_token_index (int, optional): Additional token index to ignore, such as a padding token index. Default: None.
    """

    full_state_update = False  # Make torchmetrics call update only once

    def __init__(self, dist_sync_on_step: bool = False, ignore_index: int = -100, pad_token_index: int = None):
        super().__init__(dist_sync_on_step=dist_sync_on_step)
        self.ignore_index = ignore_index
        self.pad_token_index = pad_token_index
        self.loss_fn = torch.nn.CrossEntropyLoss(reduction='none')
        self.add_state('sum_loss', default=torch.tensor(0.), dist_reduce_fx='sum')
        self.add_state('total_items', default=torch.tensor(0), dist_reduce_fx='sum')

    def update(self, output: Union[Mapping, Tensor], target: Tensor) -> None:
        if isinstance(output, Mapping):
            logits = output['logits']
        elif isinstance(output, Tensor):
            logits = output
        else:
            raise Exception(f'Type {type(output)} for the output is unsupported.')

        target = target.view(-1)
        logits = logits.view(target.shape[0], -1)
        losses = self.loss_fn(logits, target)
        # print("logits", logits.shape, logits)
        # print("target", target.shape, target)
        # Mask for ignoring both pad_token_index and ignore_index
        mask = (target != self.ignore_index)
        if self.pad_token_index is not None:
            mask &= (target != self.pad_token_index)
        # print("mask", mask.shape, mask)
        # Apply mask to losses
        masked_losses = losses * mask

        # Update total items and sum loss
        self.total_items += mask.sum()
        self.sum_loss += masked_losses.sum()

    def compute(self) -> torch.Tensor:
        """Compute the average loss and perplexity over all batches."""
        if self.total_items == 0:
            return torch.tensor(1.)
        avg_loss = self.sum_loss / self.total_items
        perplexity = torch.exp(avg_loss)
        # print("self.total_items", self.total_items)
        return perplexity


class LanguageNounPerplexity(Metric):
    def __init__(self, tokenizer, dist_sync_on_step: bool = False, ignore_index: int = -100):
        super().__init__(dist_sync_on_step=dist_sync_on_step)
        self.ignore_index = ignore_index
        self.loss_fn = nn.CrossEntropyLoss(ignore_index=ignore_index, reduction='sum')
        self.add_state('sum_noun_loss', default=torch.tensor(0.), dist_reduce_fx='sum')
        self.add_state('total_nouns', default=torch.tensor(0), dist_reduce_fx='sum')
        self.tokenizer = tokenizer
        nltk.download('averaged_perceptron_tagger')  # Ensure the POS tagger is available

    def update(self, output: Union[Mapping, torch.Tensor], target: torch.Tensor) -> None:
        # print("target", target)
        if isinstance(output, Mapping):
            logits = output['logits']
        elif isinstance(output, torch.Tensor):
            logits = output
        else:
            raise Exception(f'Type {type(output)} for the output is unsupported.')

        # Maintain the original shape of target for noun_flags
        noun_flags = torch.zeros_like(target, device=target.device)
        # noun_flags = torch.zeros(batch_size, seq_length, dtype=torch.long, device=target.device)
        # labels = np.where(labels != -100, labels, tokenizer.pad_token_id)
        pad_token_id = self.tokenizer.pad_token_id
        if pad_token_id is None:
            pad_token_id = 0
        original_pad_positions = target == -100
        target_with_pads = target.detach().clone()
        target_with_pads[original_pad_positions] = pad_token_id

        target_decoded = self.tokenizer.batch_decode(target_with_pads, clean_up_tokenization_spaces=False)

        # print("Target list", target)
        for index, target_seq in enumerate(target_decoded):
            target_seq = target_seq.replace(' <pad>', '')
            target_list = target_seq.split(' ')
            mapping ={}
            token_index = 0
            word_index=0
            for word in target_list:
                if word == '':
                    if word_index!=0:
                        token_index+=1
                    continue

                if word_index ==0:
                    word_token = self.tokenizer.batch_encode_plus([word])["input_ids"][0]
                else:
                    word_token = self.tokenizer.batch_encode_plus([' ' + word])["input_ids"][0]
                mapping[word_index] = [token_index, token_index+ len(word_token)]
                token_index+=len(word_token)
                word_index+=1
            # print(mapping)
            target_list = list(filter(None, target_list))
            pos_tag = nltk.pos_tag(target_list)
            for pos_index, pos in enumerate(pos_tag):
                # if pos[1] in ['NN', 'NNS']:
                if pos[1] in  ['NNP', 'NNPS']:
                    noun_flags[index, mapping[pos_index][0]: mapping[pos_index][1]] = 1
            # print(pos_tag)
        # Compute loss for nouns
        noun_label = target.clone().detach()
        noun_label[noun_label[:, :] == pad_token_id] = -100
        noun_label[noun_flags == 0] = -100
        # print(noun_label)

        # Reshape logits and noun_label for the loss function
        losses = self.loss_fn(logits.view(-1, logits.size(-1)), noun_label.view(-1))
        total_nouns = noun_flags.sum()

        self.total_nouns += total_nouns
        self.sum_noun_loss += losses

    def compute(self) -> torch.Tensor:
        # Handle the case where there are no nouns in the batch
        if self.total_nouns == 0:
            return torch.tensor(1.)
        return torch.exp(self.sum_noun_loss / self.total_nouns)


import unittest
import torch
from transformers import GPT2Tokenizer
# from your_module import LanguageNounPerplexity  # Import your LanguageNounPerplexity class
import torch
import unittest
from transformers import GPT2Tokenizer

class TestLanguageNounPerplexity(unittest.TestCase):
    def setUp(self):
        # Initialize tokenizer and metric
        tokenizer = GPT2Tokenizer.from_pretrained('gpt2')
        self.metric = LanguageNounPerplexity(tokenizer)

        # Prepare a batch of tokenized text
        sentences = ["The quick brown fox jumps over the lazy dog",
                     "Hello world",
                     "Harrison and Americans to check NNPS"
                     "A beautiful sunny day",
                     "Alexander the great born in the Greece"]
        tokenizer.pad_token = tokenizer.eos_token
        self.targets = tokenizer(sentences, padding=True, return_tensors="pt").input_ids

        # Simulate logits (random for the purpose of the test)
        self.logits = torch.rand(self.targets.size(0), self.targets.size(1), tokenizer.vocab_size)



    def test_perplexity_calculation(self):

        self.metric.update({'logits': self.logits}, self.targets)
        perplexity = self.metric.compute()
        print(perplexity)
        # Check if the perplexity is a valid value (not NaN, non-negative, etc.)
        self.assertTrue(torch.is_tensor(perplexity))
        self.assertFalse(torch.isnan(perplexity))
        self.assertGreaterEqual(perplexity, 0)


if __name__ == '__main__':
    unittest.main()