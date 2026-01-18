#!/usr/bin/env python3
"""
Script to import historical news data from Hugging Face datasets.
Usage: python scripts/import_history.py --dataset RealTimeData/bbc_news_alltime --config 2024-01 --limit 100
"""

import argparse
import logging
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datasets import load_dataset
from src.pipeline import IngestionPipeline

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def map_bbc_article(item):
    """Map BBC dataset fields to pipeline format."""
    # RealTimeData/bbc_news_alltime structure usually has:
    # title, description, content, url, date
    return {
        "title": item.get("title", "No Title"),
        "link": item.get("url", f"http://history/bbc/{datetime.now().timestamp()}"),
        "content": item.get("content", "") or item.get("text", ""),
        "published": item.get("date", datetime.now().isoformat()),
        "source": "BBC News Archive",
        "summary": item.get("description", "")
    }

def map_guardian_article(item):
    """Map Guardian dataset fields."""
    return {
        "title": item.get("headline", "No Title"),
        "link": item.get("webUrl", ""),
        "content": item.get("bodyText", "") or item.get("text", ""),
        "published": item.get("webPublicationDate", datetime.now().isoformat()),
        "source": "The Guardian Archive",
        "summary": item.get("trailText", "")
    }

def main():
    parser = argparse.ArgumentParser(description="Import history from Hugging Face")
    parser.add_argument("--dataset", default="RealTimeData/bbc_news_alltime", help="Hugging Face dataset ID")
    parser.add_argument("--config", default="2024-01", help="Dataset configuration/subset (e.g., YYYY-MM)")
    parser.add_argument("--limit", type=int, default=50, help="Number of articles to import")
    parser.add_argument("--dry-run", action="store_true", help="Process but do not store in DB")
    args = parser.parse_args()

    # Check for HF Token
    if not os.environ.get("HF_TOKEN") and not os.environ.get("HUGGING_FACE_HUB_TOKEN"):
        logger.warning("No HF_TOKEN found. Some datasets (like RealTimeData) may require authentication.")
        logger.warning("Export HF_TOKEN=<your_token> before running if access is denied.")

    logger.info(f"Initializing pipeline...")
    pipeline = IngestionPipeline()

    logger.info(f"Loading dataset: {args.dataset} ({args.config})...")
    try:
        # Use streaming to avoid downloading massive files
        ds = load_dataset(args.dataset, args.config, split="train", streaming=True)
    except Exception as e:
        logger.error(f"Failed to load dataset: {e}")
        return

    count = 0
    imported = 0
    skipped = 0
    alerts = 0

    logger.info(f"Starting import of {args.limit} articles...")
    
    for item in ds:
        if count >= args.limit:
            break
            
        count += 1
        
        # Determine mapper based on dataset name
        article_data = {}
        if "bbc" in args.dataset.lower():
            article_data = map_bbc_article(item)
        elif "guardian" in args.dataset.lower():
            article_data = map_guardian_article(item)
        else:
            # Generic fallback
            article_data = {
                "title": item.get("title", "Unknown"),
                "link": item.get("url", item.get("link", "")),
                "content": item.get("content", item.get("text", "")),
                "published": str(item.get("date", item.get("published", ""))),
                "source": "HF Archive"
            }

        if not article_data["content"]:
            logger.debug(f"Skipping item {count}: No content")
            continue

        logger.info(f"Processing [{count}/{args.limit}]: {article_data['title'][:50]}...")

        if args.dry_run:
            continue

        try:
            result = pipeline.process_article(article_data)
            
            if result["status"] == "imported":
                imported += 1
                if result.get("alert"):
                    alerts += 1
                    logger.info(f"🚨 ALERT TRIGGERED: {article_data['title']}")
            elif result["status"] == "skipped":
                skipped += 1
                logger.debug(f"Skipped: {result.get('reason')}")
                
        except Exception as e:
            logger.error(f"Error processing article: {e}")

    logger.info("="*40)
    logger.info(f"Import Complete")
    logger.info(f"Total Processed: {count}")
    logger.info(f"Imported:       {imported}")
    logger.info(f"Skipped:        {skipped}")
    logger.info(f"Alerts Found:   {alerts}")
    logger.info("="*40)

if __name__ == "__main__":
    main()
