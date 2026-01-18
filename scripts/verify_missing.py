#!/usr/bin/env python3
"""
Script to backfill verifications for existing articles that were missed by previous sampling.
Usage: python scripts/verify_missing.py
"""

import sys
import os
import logging
import time

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.chroma_client import NewsDatabase
from src.analysis.verification_service import VerificationService
from src.settings import load_config
from src.pipeline import IngestionPipeline # To get context loading logic

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    config = load_config("config.yaml")
    
    # Ensure verification is enabled and set to 100% in loaded config (it should be from previous edit)
    if not config.get("verification", {}).get("enabled"):
        logger.error("Verification is disabled in config.yaml")
        return

    logger.info("Initializing services...")
    db = NewsDatabase(persist_directory=config["storage"]["chroma_dir"])
    service = VerificationService(config)
    
    # Need context for verification
    context_file = config["storage"]["context_cache"]
    if os.path.exists(context_file):
        with open(context_file, "r", encoding="utf-8") as f:
            company_context = f.read()
    else:
        logger.warning("Context file not found, verification accuracy might suffer.")
        company_context = ""

    # Get all articles
    logger.info("Fetching articles from database...")
    articles = db.get_all_articles(limit=5000)
    logger.info(f"Found {len(articles)} articles in DB.")

    # Get existing verifications to skip
    recent_verifications = service.get_recent_verifications(limit=5000)
    verified_urls = set(v.get("article_url") for v in recent_verifications)
    logger.info(f"Found {len(verified_urls)} existing verification records.")

    count = 0
    errors = 0
    
    for i, article in enumerate(articles):
        url = article.get("url") or article.get("link")
        if not url:
            continue
            
        if url in verified_urls:
            continue
            
        logger.info(f"Verifying [{i+1}/{len(articles)}]: {article.get('title', 'Unknown')}")
        
        # Reconstruct article dict for service
        article_data = {
            "title": article.get("title"),
            "link": url,
            "content": article.get("summary_text", "") # We might not have full content if not cached? 
            # actually DB stores summary_text as document. 
            # Ideally we want full content.
            # Let's check cache if available.
        }
        
        # Try to load full content from cache if possible
        # We can implement a simple cache lookup here or just use summary if that's all we have.
        # The verification service takes 'content'.
        # If we only pass summary, the verification model might be confused if it expects full text.
        # But `NewsDatabase.get_all_articles` returns `summary_text` which is the `document` content in Chroma.
        # In `pipeline.py`: `text=analysis.get("summary", "")` is stored as document. 
        # Wait, strictly storing summary in vector DB is good for RAG but maybe bad for re-verification if we lose the original text.
        # However, `RSSNewsAggregator` caches the full content in `document-cache/`. 
        # We should try to read from there.
        
        # Quick and dirty cache lookup
        import hashlib
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
        cache_path = os.path.join("document-cache", f"{url_hash}.json")
        
        if os.path.exists(cache_path):
            try:
                import json
                with open(cache_path, "r") as f:
                    cached_data = json.load(f)
                    article_data["content"] = cached_data.get("content", "")
            except Exception:
                pass
        
        if not article_data.get("content"):
            # Fallback to summary from DB
            article_data["content"] = article.get("summary_text", "")

        # Prepare local result format
        local_result = {
            "relevance_score": article.get("relevance_score", 0),
            "relevance_reasoning": article.get("relevance_reasoning", ""),
            "impact_score": article.get("impact_score", 0)
        }
        
        try:
            # Force verification by setting sampling rates to 1.1 temporarily for this call?
            # Actually we updated config on disk, so `service` initialized with 1.0. 
            # But `should_verify` uses random < rate. 1.0 is inclusive? usually random() is [0.0, 1.0).
            # So 1.0 is safe.
            
            result = service.verify(article_data, local_result, company_context)
            if result:
                count += 1
                logger.info(f"Verified. Remote Score: {result.get('remote_score')}")
            else:
                logger.info("Skipped (sampling or error).")
                
            # Sleep briefly to avoid rate limits if running fast
            time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"Failed to verify: {e}")
            errors += 1

    logger.info(f"Backfill complete. Verified {count} articles. Errors: {errors}")

if __name__ == "__main__":
    main()
