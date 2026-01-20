"""Company Context Profiler."""

from __future__ import annotations

import json
import logging
import os
from textwrap import dedent
from typing import Dict, List

from bs4 import BeautifulSoup

from src.analysis.llm_client import OllamaClient
from src.settings import load_config
from src.utils import derive_company_name, default_company_structure
from src.models import CompanyContext
from src.services.scraper import fetch_company_content

logger = logging.getLogger(__name__)


class CompanyContextProfiler:
    def __init__(self, config_path: str = "config.yaml"):
        self.config = load_config(config_path)
        # Fallback for legacy single-company config if migration failed for some reason, 
        # though settings.py handles it.
        self.companies = self.config.get("companies", [])
        if not self.companies and self.config.get("company"):
             self.companies = [self.config["company"]]
        
        llm_cfg = self.config["llm"]
        from src.analysis.llm_client import LLMClient
        self.llm_client = LLMClient.create(
            provider=llm_cfg.get("provider", "ollama"),
            base_url=llm_cfg.get("base_url", "http://localhost:11434"),
            model=llm_cfg.get("model"),
            embedding_model=llm_cfg.get("embedding_model", "nomic-embed-text"),
        )

    def refresh_all_contexts(self) -> List[CompanyContext]:
        """Refresh contexts for all configured companies."""
        contexts = []
        for i, _ in enumerate(self.companies):
            try:
                ctx = self.refresh_context(i)
                contexts.append(ctx)
            except Exception as e:
                logger.error("Failed to refresh context for company index %d: %s", i, e)
        return contexts

    def refresh_context(self, index: int = 0) -> CompanyContext:
        if index < 0 or index >= len(self.companies):
            raise ValueError(f"Invalid company index: {index}")
            
        target = self.companies[index]
        url = target["url"]
        logger.info("Refreshing company context from %s", url)
        
        # Use robust scraper that includes About page
        raw_summary = fetch_company_content(url)
        if not raw_summary:
            logger.warning(f"Could not fetch content from {url}")

        # Use configured name or derive it
        company_name = target.get("name") or derive_company_name(url)
        structured = self._structure_context(raw_summary, company_name)

        context = CompanyContext(
            url=url,
            company_name=structured.get("company_name", company_name),
            raw_summary=raw_summary,
            offer_summary=structured.get("offer_summary", ""),
            business_goals=structured.get("business_goals", []),
            key_products=structured.get("key_products", []),
            market_position=structured.get("market_position", ""),
            focus_keywords=structured.get("focus_keywords", []),
        )

        # We load existing contexts to update just this one in persistence
        # Or we can just re-persist all if we have them. 
        # For simplicity, let's load current persisted state, update this index, and save.
        current_contexts = self._load_persisted_contexts()
        
        # Ensure list is long enough
        while len(current_contexts) <= index:
            current_contexts.append(None)
            
        current_contexts[index] = context
        # Filter out Nones if array was expanded
        valid_contexts = [c for c in current_contexts if c]
        
        self._persist_contexts(valid_contexts)
        return context

    def generate_broad_keywords(self) -> List[str]:
        """Generate broad, high-recall keywords based on the PRIMARY company (index 0)."""
        if not self.companies:
            return []
            
        # Ensure we have context for the primary company
        current_contexts = self._load_persisted_contexts()
        if not current_contexts:
            context = self.refresh_context(0)
        else:
            context = current_contexts[0]

        prompt = dedent(
            f"""
            You are setting up a news monitoring system for {context.company_name}.
            We need a list of BROAD, high-recall keywords to catch any potentially relevant news.
            
            Company Context:
            {context.offer_summary}
            {context.market_position}
            
            Key Products:
            {", ".join(context.key_products)}

            Task:
            Generate 10-15 broad keywords or short phrases. Include variations like "blood test" 
            if they do diagnostics, or "corporate wellness" if they do B2B.
            Do not be too specific. We want to cast a wide net.
            
            Return ONLY a JSON object with a single key "keywords" containing the list of strings.
            """
        )
        
        response = self.llm_client.generate_json(prompt)
        if not response:
            return []
            
        keywords = response.get("keywords", [])
        return [str(k).lower() for k in keywords if isinstance(k, (str, int))]
    
    def _persist_contexts(self, contexts: List[CompanyContext]) -> None:
        path = self.config["storage"]["context_cache"]
        
        # 1. Generate combined prompt for Pipeline
        lines = []
        for i, ctx in enumerate(contexts):
            role = "PRIMARY COMPANY" if i == 0 else "COMPETITOR / PEER"
            lines.append(f"=== {role}: {ctx.company_name} ===")
            lines.append(ctx.as_prompt())
            lines.append("") # Newline separator
            
        combined_prompt = "\n".join(lines)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(combined_prompt)

        # 2. Save structured data for UI
        json_path = path + ".json"
        data = {
            "companies": [
                {
                    "url": ctx.url,
                    "company_name": ctx.company_name,
                    "offer_summary": ctx.offer_summary,
                    "business_goals": ctx.business_goals,
                    "key_products": ctx.key_products,
                    "market_position": ctx.market_position,
                    "focus_keywords": ctx.focus_keywords,
                    "raw_summary": ctx.raw_summary,
                }
                for ctx in contexts
            ]
        }
        
        with open(json_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)

        logger.info(
            "Persisted %d company contexts to %s",
            len(contexts),
            path,
        )

    def _load_persisted_contexts(self) -> List[CompanyContext]:
        path = self.config["storage"]["context_cache"] + ".json"
        if not os.path.exists(path):
            return []
            
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Handle legacy single-object format
                if isinstance(data, dict) and "companies" not in data:
                     # It's a single context object
                     return [self._dict_to_context(data)]
                elif isinstance(data, dict) and "companies" in data:
                     return [self._dict_to_context(c) for c in data["companies"]]
                return []
        except Exception as e:
            logger.error(f"Error loading persisted contexts: {e}")
            return []

    def _dict_to_context(self, data: Dict) -> CompanyContext:
        return CompanyContext(
            url=data.get("url", ""),
            company_name=data.get("company_name", ""),
            raw_summary=data.get("raw_summary", ""),
            offer_summary=data.get("offer_summary", ""),
            business_goals=data.get("business_goals", []),
            key_products=data.get("key_products", []),
            market_position=data.get("market_position", ""),
            focus_keywords=data.get("focus_keywords", []),
        )

    def _fetch_html(self, url: str) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return response.text

    def _extract_section(self, soup: BeautifulSoup, keywords) -> str:
        for keyword in keywords:
            section = soup.find(
                lambda tag: tag.name in {"section", "div", "p", "article"}
                and keyword in tag.get_text(strip=True).lower()
            )
            if section:
                return section.get_text(strip=True)
        return ""

    def _structure_context(
        self, raw_text: str, company_name: str
    ) -> Dict[str, List[str] | str]:
        if not raw_text.strip():
            return self._fallback_structure(company_name)

        # Truncate text to avoid context limits (approx 3-4k tokens)
        truncated_text = raw_text[:12000]

        prompt = dedent(
            f"""
            You are a strategy consultant. Convert the marketing copy below into
            actionable business intelligence for relevance scoring. Return ONLY JSON
            with these fields:
            - company_name: string name of the business
            - offer_summary: 1-2 sentence summary of the core offering and who it serves
            - business_goals: list[str] of 3-5 measurable objectives
            - key_products: list[str] describing the main services or packages
            - market_position: string summarizing niche, differentiation, and target market
            - focus_keywords: list[str] of 5-8 lower-case keywords/phrases to match against articles
            
            Text:
            {truncated_text}
            """
        )

        response = self.llm_client.generate_json(prompt)
        defaults = self._fallback_structure(company_name)

        if not response:
            logger.warning("LLM failed to structure company context; using fallback")
            return defaults

        # Merge with defaults if LLM returns empty values
        return {
            "company_name": response.get("company_name") or defaults["company_name"],
            "offer_summary": response.get("offer_summary") or defaults["offer_summary"],
            "business_goals": response.get("business_goals") or defaults["business_goals"],
            "key_products": response.get("key_products") or defaults["key_products"],
            "market_position": response.get("market_position") or defaults["market_position"],
            "focus_keywords": response.get("focus_keywords") or defaults["focus_keywords"],
        }

    def _fallback_structure(self, company_name: str) -> Dict[str, List[str] | str]:
        # Use shared default structure logic
        return default_company_structure(self.config, company_name)
