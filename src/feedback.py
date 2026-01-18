"""Utilities for recording tag feedback and applying it to future tagging."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Set


def _ensure_parent(path: str) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)


def append_feedback(path: str, payload: Dict[str, str]) -> None:
    _ensure_parent(path)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_feedback(path: str) -> List[Dict[str, str]]:
    if not os.path.exists(path):
        return []

    records: List[Dict[str, str]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def get_bad_tags(path: str) -> Set[str]:
    bad_tags: Set[str] = set()
    for record in load_feedback(path):
        tag = str(record.get("tag", "")).strip().lower()
        verdict = str(record.get("verdict", "bad")).lower()
        if tag and verdict in {"bad", "irrelevant", "remove"}:
            bad_tags.add(tag)
    return bad_tags


def filter_tags(tags: Iterable[str], bad_tags: Set[str]) -> List[str]:
    return [tag for tag in tags if tag.strip().lower() not in bad_tags]
