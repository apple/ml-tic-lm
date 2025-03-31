# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
# 

import os
import re
import json

np_versions = {
    "1.13.0": "06/2017",
    "1.14.0": "01/2018",
    "1.15.0": "07/2018",
    "1.16.0": "01/2019",
    "1.17.0": "07/2019",
    "1.18.0": "12/2019",
    "1.19.0": "06/2020",
    "1.20.0": "01/2021",
    "1.21.0": "06/2021",
    "1.22.0": "12/2021",
    "1.23.0": "06/2022",
    "1.24.0": "12/2022",
    "1.25.0": "06/2023",
    "1.26.0": "09/2023",
    "2.0.0": "06/2024",
    "2.1.0": "08/2024",
    "2.2.0": "12/2024",
}


def find_html_files(directory) -> list[str]:
    html_files = []

    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".html"):
                html_files.append(os.path.join(root, file))

    return html_files


def remove_special_spaces(text):
    pattern = r' —\s+\n\s*'
    return re.sub(pattern, '', text, flags=re.MULTILINE)

def postprocess(doc: str, v: str) -> str:
    major, minor, _ = v.split(".")
    extras = [
        f"NumPy v{major}.{minor} Manual",
    ]
    for e in extras:
        doc = doc.replace(e, "")
    # doc = remove_special_spaces(doc)
    # doc = clean_newlines(doc)
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


def remove_copyright(text):
    # Pattern for special substrings with dash and newlines
    pattern1 = r' —\s+\n\s*'
    # Pattern for copyright string
    pattern2 = r'© Copyright \d{4}-\d{4}, NumPy Developers\.\s*'
    # Pattern for Sphinx version string
    pattern3 = r'Created using Sphinx \d+\.\d+\.\d+\.\s*'
    # Combine all patterns
    patterns = [pattern1, pattern2, pattern3]
    # Apply all patterns
    for pattern in patterns:
        text = re.sub(pattern, '', text, flags=re.MULTILINE)
    
    return text

def clean_newlines(text):
    # Pattern to match more than two newlines with optional whitespace
    pattern = r'(\n\s*){3,}'

    # Replace throughout the entire text
    cleaned_text = re.sub(pattern, '\n\n', text)

    return cleaned_text

def should_include(title: str, text: str) -> bool:
    if len(text) < 20:
        return False

    return True
    

def save_jsonl(data: list[dict], v: str):
    month, year = np_versions[v].split("/")
    save_path = f"./output/numpy/{year}{month}.jsonl"
    with open(save_path, "w") as f:
        for d in data:
            f.write(json.dumps(d, ensure_ascii=False)+"\n")
    print(f"saved all docs at {save_path}")

def generate(v: str, method: str):
    assert v in np_versions
    assert method in ['readability', 'trafilatura']
    # find docs
    root = f"./output/numpy/v{v}_{method}"
    print(f"collecting docs from {root=}")
    extract_dirs = [os.path.join(root, d) for d in ["reference", "user"]]
    htmls = []
    for ed in extract_dirs:
        htmls += find_html_files(ed)
    print(f"found {len(htmls)} html docs")
    
    texts = []
    for html in htmls:
        title = html.replace(".html", "")
        title = title.replace(root, "")
        text = get_text(html)
        if len(text.replace('\n','').replace('  ','')) < 25:
            continue
        # text = remove_copyright(text)
        # text = postprocess(text, v).strip()
        if should_include(title, text):
            texts.append({"title": title, "text": text})
    print(f"found {len(texts)} texts docs")

    save_jsonl(texts, v)



if __name__ == "__main__":
    import sys

    version = sys.argv[1] # e.g., 2.2.0
    method = sys.argv[2]  # e.g., readability
    generate(version, method)

