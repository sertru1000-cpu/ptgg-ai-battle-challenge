"""Card ID -> name/category lookup, sourced from the official EN Card Data.csv.

The CSV is UTF-8 encoded (curly apostrophes etc. are valid 3-byte UTF-8, e.g.
b'\\xe2\\x80\\x99' = U+2019). A handful of bytes elsewhere in the file are not valid
UTF-8 (cause of the header's "Pok\\ufffdmon" mangling), hence errors="replace" -- do
NOT switch to cp1252/latin-1, which decodes the valid multi-byte UTF-8 sequences
(like the apostrophes) into mojibake instead and silently drops rows (confirmed:
cp1252 read yields 2022 rows / wrong card names, utf-8+replace yields the correct
1267-row card pool matching the verified card-pool count from Part 0).
"""
from __future__ import annotations

import csv
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CARD_DATA_PATH = os.path.join(REPO_ROOT, "data", "official", "EN Card Data.csv")

_cache = None


def load_card_data() -> dict[int, dict]:
    global _cache
    if _cache is not None:
        return _cache
    table = {}
    with open(CARD_DATA_PATH, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cid_key = next(k for k in row if "Card ID" in k)
            try:
                cid = int(row[cid_key])
            except (ValueError, TypeError):
                continue
            table[cid] = row
    _cache = table
    return table


def name_of(card_id: int) -> str:
    table = load_card_data()
    row = table.get(card_id)
    return row["Card Name"] if row else f"<unknown:{card_id}>"


def category_of(card_id: int) -> str:
    table = load_card_data()
    row = table.get(card_id)
    return row.get("Category", "") if row else ""
