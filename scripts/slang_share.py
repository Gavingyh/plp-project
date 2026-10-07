"""
How many labelled train/dev sentences hold Singlish, internet slang, a chat
abbreviation or an emoji. Behind the 6 Oct 2026 decision not to build a slang
dictionary before domain-adaptive pretraining (docs/evidence/dapt-2026-10-06.md).
The word list is deliberately generous (it counts "u" and "DCA"), so the share
it gives is an upper bound. Reads only train/dev rows, never test text.

USAGE (from the repository root):
  .venv-plp/bin/python3 scripts/slang_share.py [labels.csv]
"""

import collections
import re
import sys

import pandas as pd

SLANG = re.compile(
    r"\b(?:lah|leh|lor|meh|liao|sia|jialat|shiok|sian|walao|wah|alamak|paiseh|kiasu|bo|nerf|buff|lol|lmao|tbh|imo"
    r"|iirc|smh|dca|stonks|fomo|yolo|huat|onz|cmi|abit|liddat|dun|wan|cos|coz|ur|u|pls|plz|thx|tho)\b"
    r"|😂|🤣|😭|🙄|😅|👍", re.IGNORECASE)


def share(path: str = "data/labeled/combined/candidates_resolved.csv") -> dict:
    rows = pd.read_csv(path)
    train = rows[rows["split"] == "train_dev"]
    hit = train[train["text"].astype(str).str.contains(SLANG)]
    words = collections.Counter(m.group(0).lower() for t in hit["text"] for m in SLANG.finditer(t))
    return {"train_dev_rows": len(train), "with_slang": len(hit),
            "share": round(len(hit) / max(len(train), 1), 3), "commonest": words.most_common(10)}


if __name__ == "__main__":
    print(share(*sys.argv[1:]))
