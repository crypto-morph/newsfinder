import argparse
import logging
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.aggregator.sitemap import SitemapBackfiller
from src.pipeline import IngestionPipeline
from src.settings import load_config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("backfill_cli")

def main():
    parser = argparse.ArgumentParser(description="Backfill BBC News from Sitemaps")
    parser.add_argument("month", help="Target month (YYYY-MM)")
    parser.add_argument("--limit", type=int, default=50, help="Max articles to process")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    
    args = parser.parse_args()
    
    try:
        year, month = map(int, args.month.split("-"))
    except ValueError:
        logger.error("Invalid month format. Use YYYY-MM")
        return

    logger.info(f"Starting backfill for {args.month} (Limit: {args.limit})")
    
    # 1. Discover
    backfiller = SitemapBackfiller()
    urls = backfiller.get_urls_for_month(year, month)
    
    if not urls:
        logger.info("No articles found.")
        return
        
    logger.info(f"Found {len(urls)} URLs. Processing top {args.limit}...")
    urls = urls[:args.limit]
    
    # 2. Process
    pipeline = IngestionPipeline(args.config)
    
    success = 0
    for i, url in enumerate(urls):
        try:
            logger.info(f"[{i+1}/{len(urls)}] Processing {url}")
            
            # Scrape
            meta_holder = {"is_slug_title": True}
            content = pipeline.aggregator._scrape_article_content(url, metadata=meta_holder)
            
            if content:
                title = meta_holder.get("title")
                if not title or meta_holder.get("is_slug_title"):
                    title = url.split("/")[-1].replace("-", " ").title()
                
                article_data = {
                    "title": title,
                    "link": url,
                    "published": f"{args.month}-01",
                    "content": content,
                    "source": "BBC Archive",
                    "is_slug_title": False
                }
                
                result = pipeline.process_article(article_data)
                if result["status"] == "imported":
                    success += 1
                    logger.info(f"  -> Imported: {title}")
                else:
                    logger.info(f"  -> Skipped: {result.get('reason')}")
            else:
                logger.warning("  -> Failed to scrape content")
                
        except Exception as e:
            logger.error(f"  -> Error: {e}")
            
    logger.info(f"Backfill complete. Imported {success}/{len(urls)}.")

if __name__ == "__main__":
    main()
