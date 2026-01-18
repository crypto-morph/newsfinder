"""Core ingestion pipeline orchestrator."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List

from src.analysis.llm_client import OllamaClient
from src.analysis.verification_service import VerificationService
from src.aggregator.rss_scraper import RSSNewsAggregator
from src.database.chroma_client import NewsDatabase
from src.settings import load_config
from src.history import HistoryManager

logger = logging.getLogger(__name__)


class IngestionPipeline:
    def __init__(self, config_path: str = "config.yaml"):
        self.config = load_config(config_path)
        feeds = self.config.get("feeds", [])
        # Enable document caching to speed up re-runs
        self.aggregator = RSSNewsAggregator(
            feed_urls=feeds, 
            cache_dir="document-cache"
        )
        self.llm_client = OllamaClient(
            base_url=self.config["llm"]["base_url"],
            model=self.config["llm"]["model"],
            embedding_model=self.config["llm"]["embedding_model"],
        )
        self.verification_service = VerificationService(self.config)
        chroma_dir = self.config["storage"]["chroma_dir"]
        self.db = NewsDatabase(persist_directory=chroma_dir)
        self.history_manager = HistoryManager()

    def _article_id(self, url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    def fetch(self) -> List[Dict]:
        """Fetch raw articles from all configured feeds."""
        limit = self.config["pipeline"].get("articles_per_feed", 3)
        
        # Callback to check if article already exists in DB
        def skip_if_exists(url: str) -> bool:
            # We use the same ID generation logic as process_article
            article_id = self._article_id(url)
            return self.db.article_exists(article_id)

        return self.aggregator.fetch_recent_articles(
            limit_per_feed=limit, 
            skip_callback=skip_if_exists
        )

    def process_article(self, article: Dict, force: bool = False) -> Dict:
        """
        Process a single article: deduplicate, filter, analyze, embed, store.
        Returns a result dict with status and details.
        """
        result = {
            "status": "pending",
            "title": article.get("title"),
            "url": article.get("link"),
            "reason": None
        }

        # 1. Deduplication
        article_id = self._article_id(article["link"])
        if not force and self.db.article_exists(article_id):
            result["status"] = "skipped"
            result["reason"] = "Duplicate (already exists in DB)"
            logger.info("Skipping duplicate article %s", article["link"])
            return result

        # 2. Keyword Filtering
        keywords = set(
            kw.lower() for kw in self.config["pipeline"].get("keywords", [])
        )
        content_lower = article["content"].lower()
        if not force and keywords and not any(keyword in content_lower for keyword in keywords):
            result["status"] = "skipped"
            result["reason"] = "Filtered (no matching keywords)"
            logger.debug("Skipping article %s due to keyword filter", article.get("title"))
            return result

        # 3. LLM Analysis
        company_context = self._load_company_context()
        analysis = self.llm_client.analyze_article(
            article["content"], context=company_context
        )
        
        # 3b. LLM Verification (OpenRouter)
        self.verification_service.verify(
            article=article,
            local_result=analysis,
            context=company_context
        )
        
        # 4. Topic Extraction
        topic_tags = self.llm_client.extract_topics(article["content"])
        
        # 5. Embedding
        embedding = self.llm_client.generate_embedding(analysis.get("summary", ""))

        # 6. Metadata Construction
        metadata = {
            "url": article["link"],
            "title": article["title"],
            "published_date": article["published"],
            "source": article["source"],
            "relevance_score": analysis.get("relevance_score", 0),
            "relevance_reasoning": analysis.get("relevance_reasoning", ""),
            "impact_score": analysis.get("impact_score", 0),
            "summary_text": analysis.get("summary", ""),
            "key_entities": analysis.get("key_entities", []),
            "topic_tags": topic_tags,
            # Reappraisal tracking
            "previous_relevance_score": article.get("previous_relevance_score"),
            "previous_impact_score": article.get("previous_impact_score"),
            "reappraised_count": article.get("reappraised_count", 0),
        }

        # 7. Storage
        self.db.add_article(
            article_id=article_id,
            text=analysis.get("summary", ""),
            embedding=embedding,
            metadata=metadata,
        )

        # 8. Alerting
        alert_cfg = self.config["pipeline"].get("alert_threshold", {})
        relevance_cutoff = alert_cfg.get("relevance", 7)
        impact_cutoff = alert_cfg.get("impact", 7)

        if (
            metadata["relevance_score"] >= relevance_cutoff
            and metadata["impact_score"] >= impact_cutoff
        ):
            self._log_alert(metadata)
            result["alert"] = True

        result["status"] = "imported"
        result["metadata"] = metadata
        return result

    def reprocess_article(self, article_id: str) -> Dict:
        """
        Re-run analysis for a specific article by ID.
        """
        # 1. Get existing metadata to find URL
        existing = self.db.get_article(article_id)
        if not existing:
            return {"status": "error", "message": "Article not found"}
            
        url = existing.get("url")
        if not url:
            return {"status": "error", "message": "Article has no URL"}

        # 2. Re-fetch content
        # We need to construct a minimal metadata dict for the scraper if needed
        meta = {
            "title": existing.get("title", ""),
            "published": existing.get("published", ""),
            "source": existing.get("source", ""),
        }
        
        # This will check Archive/Parquet first, then scrape
        content = self.aggregator._scrape_article_content(url, metadata=meta)
        
        # Fallback: If scraping fails/cache missing, use stored summary
        is_fallback = False
        if not content:
            logger.warning(f"Could not retrieve original content for {article_id}. Falling back to stored summary.")
            content = existing.get("summary_text", "")
            is_fallback = True
            
        if not content:
             return {"status": "error", "message": "Could not retrieve content or summary"}

        # 3. Construct article dict for pipeline
        article_data = {
            "title": existing.get("title", ""),
            "link": url,
            "published": existing.get("published", ""),
            "content": content,
            "source": existing.get("source", ""),
            # Carry over previous scores for comparison
            "previous_relevance_score": existing.get("relevance_score"),
            "previous_impact_score": existing.get("impact_score"),
            "reappraised_count": existing.get("reappraised_count", 0) + 1,
            "is_content_fallback": is_fallback
        }

        # 4. Force process
        logger.info(f"Reprocessing article {article_id} ({url})")
        result = self.process_article(article_data, force=True)
        
        if result.get("status") == "imported":
            new_metadata = result.get("metadata", {})
            # Log history
            changes = self.history_manager.log_change(article_id, existing, new_metadata)
            result["history_diff"] = changes
            
        return result

    def run(self) -> List[Dict]:
        """Legacy run method for backward compatibility."""
        articles = self.fetch()
        processed: List[Dict] = []
        seen_urls: set[str] = set()

        for article in articles:
            if article["link"] in seen_urls:
                continue
            seen_urls.add(article["link"])

            result = self.process_article(article)
            if result["status"] == "imported":
                processed.append(result["metadata"])

        self.update_status(len(processed))
        return processed

    def _load_company_context(self) -> str:
        context_file = self.config["storage"]["context_cache"]
        try:
            with open(context_file, "r", encoding="utf-8") as handle:
                return handle.read()
        except FileNotFoundError:
            logger.warning("Context cache not found; run profiler to refresh context.")
            return ""

    def _log_alert(self, metadata: Dict) -> None:
        alerts_log = self.config["storage"]["alerts_log"]
        timestamp = datetime.now(timezone.utc).isoformat()
        line = json.dumps({"timestamp": timestamp, **metadata}, ensure_ascii=False)
        with open(alerts_log, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        logger.info(
            "Alert logged for article %s (relevance %s, impact %s)",
            metadata.get("title"),
            metadata.get("relevance_score"),
            metadata.get("impact_score"),
        )

    def update_status(self, articles_processed: int) -> None:
        status_file = self.config["storage"]["status_file"]
        status = {
            "last_run": datetime.now(timezone.utc).isoformat(),
            "articles_processed": articles_processed,
        }
        with open(status_file, "w", encoding="utf-8") as handle:
            json.dump(status, handle)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    pipeline = IngestionPipeline()
    pipeline.run()
