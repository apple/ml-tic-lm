# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
# 

import os
import sys
import json

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
    "2.5.0": "10/2024",
    "2.6.0": "01/2025",
}

MIN_LEN = 25


def find_html_files(directory) -> list[str]:
    html_files = []
    filters = ["genindex", "FXE00"]

    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".html"):
                use = True
                for f in filters:
                    if f in file:
                        use = False
                if use:
                    html_files.append(os.path.join(root, file))

    return html_files


def postprocess(doc: str, v: str) -> str:
    return doc.strip()


def get_text(html_path: str):
    text_path = html_path + ".txt"
    try:
        with open(text_path, "r") as f:
            text = f.read()
        return text
    except Exception:
        print(f"html={html_path}, text={text_path}")
        return ""


def save_jsonl(data: list[dict], v: str):
    month, year = torch_versions[v].split("/")
    save_path = f"./output/pt_{year}{month}.jsonl"
    with open(save_path, "w") as f:
        for d in data:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"saved all docs at {save_path}")


def generate(v: str, method: str):
    assert v in torch_versions
    assert method in ['readability', 'trafilatura']
    # find docs
    root = f"./output/torch_{v}_{method}/"
    extract_dirs = [os.path.join(root, d) for d in ["notes", "generated"]]
    search_dirs = [root] + extract_dirs
    htmls = []
    for ed in search_dirs:
        htmls += find_html_files(ed)
    print(f"found {len(htmls)} html docs")

    texts = []
    for html in htmls:
        title = html.replace(".html", "")
        title = title.replace(root, "")
        text = get_text(html)
        if len(text) < MIN_LEN:
            continue
        text = postprocess(text, v)
        texts.append({"title": title, "text": text})
    print(f"found {len(texts)} texts docs")

    save_jsonl(texts, v)


if __name__ == "__main__":
    import sys

    version = sys.argv[1] # e.g., 2.6.0
    method = sys.argv[2]  # e.g., readability
    generate(version, method)
