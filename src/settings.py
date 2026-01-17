"""Configuration helpers for the News Finder project."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

import yaml


DEFAULT_CONFIG: Dict[str, Any] = {
    "companies": [{"name": "BBC", "url": "https://www.bbc.com"}],
    "feeds": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://feeds.bbci.co.uk/news/technology/rss.xml",
        "https://www.theguardian.com/uk/rss",
    ],
    "pipeline": {
        "articles_per_feed": 3,
        "keywords": ["ai", "artificial intelligence", "machine learning", "automation"],
        "alert_threshold": {"relevance": 7, "impact": 7},
    },
    "llm": {
        "base_url": "http://localhost:11434",
        "model": "LiquidAI/LFM2.5-1.2B-Instruct",
        "embedding_model": "nomic-embed-text",
    },
    "storage": {
        "chroma_dir": "chroma_db",
        "alerts_log": "logs/alerts.log",
        "status_file": "logs/status.json",
        "context_cache": "logs/company_context.txt",
        "feedback_log": "logs/tag_feedback.jsonl",
    },
    "scheduler": {"enabled": True, "interval_minutes": 60},
    "web": {"host": "0.0.0.0", "port": 5000},
}


def _deep_update(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in overrides.items():
        if (
            key in base
            and isinstance(base[key], dict)
            and isinstance(value, dict)
        ):
            base[key] = _deep_update(base[key], value)
        else:
            base[key] = value
    return base


def _ensure_parent_dir(path: Path) -> None:
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)


def derive_feed_name(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.netloc or parsed.path).replace("www.", "")
    host_label = host.split(".")[0].replace("-", " ").title() if host else ""
    if "bbc" in host:
        host_label = "BBC"
    elif "guardian" in host:
        host_label = "Guardian"

    path_parts = [part for part in parsed.path.split("/") if part]
    segment = ""
    if path_parts:
        tail = path_parts[-1]
        segment = path_parts[-2] if "." in tail and len(path_parts) > 1 else tail
        segment = segment.replace("-", " ").title()

    if host_label and segment:
        return f"{host_label} {segment}".strip()
    return host_label or segment or url


def normalize_feeds(feeds: List[Any]) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    for entry in feeds or []:
        if isinstance(entry, str):
            url = entry.strip()
            if not url:
                continue
            normalized.append({"name": derive_feed_name(url), "url": url})
        elif isinstance(entry, dict):
            url = str(entry.get("url", "")).strip()
            if not url:
                continue
            name = str(entry.get("name", "")).strip() or derive_feed_name(url)
            normalized.append({"name": name, "url": url})
    return normalized


def load_config(path: str | os.PathLike[str] = "config.yaml") -> Dict[str, Any]:
    """Load configuration from disk and merge with defaults."""

    config_path = Path(path)
    config = copy.deepcopy(DEFAULT_CONFIG)

    if config_path.exists():
        with config_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
            _deep_update(config, data)

    # Migration: company -> companies
    if "company" in config:
        if isinstance(config["company"], dict) and config["company"].get("url"):
            # If companies list is empty or default, overwrite with legacy single company
            # If user already has companies list, we might want to append or ignore. 
            # Let's assume if 'company' is present, it takes precedence if 'companies' is default.
            
            # Check if companies is still the default value
            if config["companies"] == DEFAULT_CONFIG["companies"]:
                config["companies"] = []
            
            # Add legacy company if not already in list
            legacy_url = config["company"]["url"]
            if not any(c.get("url") == legacy_url for c in config["companies"]):
                config["companies"].insert(0, {
                    "name": "Primary Company", # Placeholder, will be derived or updated
                    "url": legacy_url
                })
        
        # Remove legacy key to avoid confusion
        del config["company"]

    config["feeds"] = normalize_feeds(config.get("feeds", []))

    for key in ("alerts_log", "status_file", "context_cache"):
        file_path = Path(config["storage"][key])
        _ensure_parent_dir(file_path)

    config["config_path"] = str(config_path.resolve())
    return config
