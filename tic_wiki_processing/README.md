# TiC-Wiki Processing

This repository contains tools for processing and analyzing temporal changes in Wikipedia and Wikidata.

## Directory Structure

- **wikipedia**: Contains scripts for processing Wikipedia dumps to identify content changes over time. This is used for perplexity evaluations with LLM-Foundry.
  
- **wikidata_alignment**: Contains scripts for processing Wikidata dumps and aligning them with Wikipedia evidence. This is used for generating question-answering (QA) evaluations.

## Processing Order

Each directory contains its own detailed README with specific instructions:

1. Run the Wikipedia processing scripts if you need perplexity evaluation data.
2. The Wikidata alignment scripts can be run independently, but it require the changed/unchaged snapshots of Wikipedia from above step if you need QA evaluation data.

## Output Formats

### Wikipedia Output (for perplexity evaluations)

The final output is in JSONL format suitable for LLM-Foundry evaluations.


### Wikidata Alignment Output (for QA evaluations)

Note: This evaluation is not used in the TiC-LM paper.

The final output for LLM question-answering evaluation is in JSON format for each two consecutive months:

```json
{
    "context": "Question: Fill in the blank: Douglas Adams' most notable work is _______. Answer:",
    "answer": "The Hitchhiker's Guide to the Galaxy",
    "aliases": ["Hitchhiker's Guide to the Galaxy", "The Hitchhiker's Guide", "HHGTTG"],
    "metadata": {
        "relation": "notable work"
    }
}
```

For detailed instructions on how to generate each dataset, please refer to the README in each respective directory.
