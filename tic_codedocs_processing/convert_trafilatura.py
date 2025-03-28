# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
# 

import sys
from trafilatura import  extract

def clean(txt:str) -> str:
    txt = txt.replace("¶","")
    return txt

def convert(in_path: str):
    out_path = in_path + ".txt"
    html = open(in_path, "r", encoding="utf-8").read()
    text = extract(html, include_comments=False, favor_recall=True)
    text = clean(str(text))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)

if __name__ == "__main__":
    path = sys.argv[1]
    convert(path)
