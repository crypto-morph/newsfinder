import os
import json
import copy
from typing import Dict, Any, List
from flask import current_app, g
from urllib.parse import urlparse
from pathlib import Path
import yaml

from src.settings import load_config
from src.database.chroma_client import NewsDatabase
from src.analysis.llm_client import OllamaClient
from src.event_logger import EventLogger
from src.utils import derive_company_name, default_company_structure

# Global event logger
event_logger = EventLogger()

NAV_LINKS = [
    {"label": "Dashboard", "endpoint": "dashboard.dashboard", "icon": "mdi-view-dashboard"},
    {"label": "Articles", "endpoint": "articles.articles_view", "icon": "mdi-file-document-multiple-outline"},
    {"label": "LLM Verification", "endpoint": "verification.verification_view", "icon": "mdi-shield-check"},
    {"label": "RAG Explorer", "endpoint": "explore.explore", "icon": "mdi-magnify"},
    {"label": "Sources", "endpoint": "config.sources", "icon": "mdi-rss"},
    {"label": "Import", "endpoint": "import_routes.import_view", "icon": "mdi-cloud-download"},
    {"label": "Config & Context", "endpoint": "config.config_view", "icon": "mdi-cog-outline"},
]

def current_config() -> Dict[str, Any]:
    return current_app.config["NEWSFINDER_CONFIG"]

def get_db() -> NewsDatabase:
    if "news_db" not in g:
        cfg = current_config()
        chroma_dir = cfg["storage"]["chroma_dir"]
        g.news_db = NewsDatabase(persist_directory=chroma_dir)
    return g.news_db

def build_ollama(cfg: Dict[str, Any]):
    from src.analysis.llm_client import LLMClient
    llm_cfg = cfg["llm"]
    return LLMClient.create(
        provider=llm_cfg.get("provider", "ollama"),
        base_url=llm_cfg.get("base_url", "http://localhost:11434"),
        model=llm_cfg.get("model"),
        embedding_model=llm_cfg.get("embedding_model", "nomic-embed-text"),
    )

def load_status(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data or {"last_run": "—", "articles_processed": 0}
    except (FileNotFoundError, json.JSONDecodeError):
        return {"last_run": "—", "articles_processed": 0}

def load_alerts(path: str, limit: int = 5) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []

    alerts: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle.readlines()[-limit:]:
            try:
                alerts.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue
    alerts.reverse()
    return alerts

def load_context(path: str) -> Dict[str, Any]:
    prompt = ""
    structured: Dict[str, Any] | None = None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            prompt = handle.read()
    except FileNotFoundError:
        prompt = "Context not generated yet."

    json_path = path + ".json"
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as handle:
            structured = json.load(handle)

    return {
        "prompt": prompt,
        "structured": structured,
    }

def save_config(new_config: Dict[str, Any]) -> None:
    config_path = new_config.get("config_path") or current_config().get("config_path")
    if not config_path:
        raise ValueError("Config path is not set")

    # Remove runtime-only entries
    cleaned = copy.deepcopy(new_config)
    cleaned.pop("config_path", None)

    with open(config_path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(cleaned, handle, sort_keys=False, allow_unicode=True)

    current_app.config["NEWSFINDER_CONFIG"] = load_config(config_path)

def enrich_context(context: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    structured = context.get("structured") or {}
    
    # Handle new multi-company format
    if "companies" in structured and isinstance(structured["companies"], list):
        pass 
    else:
        # Legacy or empty: Try to migrate or init from config
        cfg_companies = cfg.get("companies", [])
        if not cfg_companies and cfg.get("company"):
             cfg_companies = [cfg["company"]]
             
        structured_companies = []
        
        # If we have legacy structured data, maybe we can use it for the first company
        legacy_data = structured if structured.get("company_name") else None
        
        for idx, comp_cfg in enumerate(cfg_companies):
            if idx == 0 and legacy_data:
                # Use existing data for primary
                structured_companies.append(legacy_data)
            else:
                # Create default/empty placeholder
                structured_companies.append(default_company_structure(cfg, comp_cfg.get("name", "Company"), comp_cfg.get("url", "")))
        
        structured = {"companies": structured_companies}

    context["structured"] = structured
    return context
