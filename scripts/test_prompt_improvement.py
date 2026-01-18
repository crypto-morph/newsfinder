#!/usr/bin/env python3
"""
Script to test prompt improvements on specific problematic articles.
"""

import sys
import os
import logging
import argparse
from datasets import load_dataset

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.analysis.llm_client import OllamaClient
from src.settings import load_config
from src.pipeline import IngestionPipeline

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Dynamic Distractors to look for
DISTRACTOR_KEYWORDS = [
    "Football", "Cricket", "Tennis", "Celebrity", "Movie", "Star", "Album", "Concert"
]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="2026-01", help="Dataset config (YYYY-MM)")
    args = parser.parse_args()

    config = load_config("config.yaml")
    
    # Initialize LLM Client
    llm = OllamaClient(
        base_url=config["llm"]["base_url"],
        model=config["llm"]["model"],
        embedding_model=config["llm"]["embedding_model"]
    )
    
    # Load company context
    pipeline = IngestionPipeline()
    context = pipeline._load_company_context()

    logger.info(f"Fetching content from Hugging Face (BBC News {args.config})...")
    try:
        ds = load_dataset("RealTimeData/bbc_news_alltime", args.config, split="train", streaming=True)
    except Exception as e:
        logger.error(f"Failed to load dataset: {e}")
        return

    logger.info("Scanning for 'Distractor' articles (Sports/Entertainment)...")
    
    test_articles = []
    count = 0
    search_limit = 500
    
    for item in ds:
        count += 1
        if count > search_limit:
            break
            
        title = item.get("title", "")
        content = item.get("content", "") or item.get("text", "")
        
        # Check if this is a good distractor
        if any(k in title for k in DISTRACTOR_KEYWORDS):
            # Only pick if it doesn't explicitly mention "Health" or "Hospital" in title
            if "Health" not in title and "Hospital" not in title:
                test_articles.append({"title": title, "content": content})
                if len(test_articles) >= 5:
                    break
    
    logger.info(f"Found {len(test_articles)} distractor articles.")
    logger.info("-" * 60)

    passed = 0
    
    for article in test_articles:
        title = article["title"]
        logger.info(f"Analyzing: {title}")
        logger.info("  Expected Score: Low (0-3)")
        
        analysis = llm.analyze_article(article["content"], context)
        score = analysis.get("relevance_score", 0)
        reasoning = analysis.get("relevance_reasoning", "")
        
        status = "✅ PASS" if score <= 3 else "❌ FAIL"
        if score <= 3:
            passed += 1
            
        logger.info(f"  Score: {score} {status}")
        logger.info(f"  Reasoning: {reasoning}")
        logger.info("-" * 60)

    logger.info(f"Summary: {passed}/{len(test_articles)} Passed")

if __name__ == "__main__":
    main()
