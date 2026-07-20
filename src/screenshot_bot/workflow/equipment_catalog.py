"""Reads the equipment catalog CSV (columns: category, equipment, path) -- the same file
scripts/screenshot_equipment_list.py already reads for offline batch capture. Re-read from disk
on every call rather than cached: the CSV is small (tens to low hundreds of rows) and this way is
always current, with no cache-invalidation to get wrong. A missing/unreadable file surfaces as a
plain OSError, left for the caller to decide how to handle (see WeChatImageReplyWorkflow, which
treats it the same as an empty catalog)."""

import csv


def load_categories(csv_path):
    """Category names in first-seen CSV order (stable, not alphabetized) -- this becomes the
    numbered list a sender picks from, so the order should match however the CSV was produced."""
    seen = []
    seen_set = set()
    with open(csv_path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            category = row.get("category", "")
            if category and category not in seen_set:
                seen_set.add(category)
                seen.append(category)
    return seen


def load_equipment(csv_path, category):
    """Equipment rows for one category, in CSV order, as [{"equipment": ..., "path": ...}, ...]."""
    items = []
    with open(csv_path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row.get("category", "") == category:
                items.append({"equipment": row.get("equipment", ""), "path": row.get("path", "")})
    return items
