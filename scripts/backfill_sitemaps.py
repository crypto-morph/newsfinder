import requests
import logging
import argparse
from datetime import datetime
import dateutil.parser
from bs4 import BeautifulSoup
import sys
import os
import time

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.aggregator.rss_scraper import RSSNewsAggregator
from src.archive_manager import ArchiveManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("backfill_sitemaps")

SITEMAP_INDEXES = [
    "https://www.bbc.co.uk/sitemaps/https-index-uk-news.xml",
    "https://www.bbc.co.uk/sitemaps/https-index-uk-archive.xml"
]

def fetch_sitemap_urls(start_date: datetime, end_date: datetime, limit: int = None) -> list[dict]:
    """
    Crawls BBC sitemaps to find article URLs within the date range.
    Returns a list of dicts: {url, title, published}
    """
    found_articles = []
    
    for index_url in SITEMAP_INDEXES:
        if limit and len(found_articles) >= limit:
            break
            
        logger.info(f"Fetching sitemap index: {index_url}")
        try:
            resp = requests.get(index_url, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, "xml")
            
            sitemaps = soup.find_all("sitemap")
            logger.info(f"Found {len(sitemaps)} sub-sitemaps in index.")
            
            # Process sitemaps in reverse order (newest first) to find recent articles faster
            # This is often better for backfilling "gaps" to "now"
            for sm in reversed(sitemaps):
                if limit and len(found_articles) >= limit:
                    break

                loc = sm.find("loc").text
                lastmod_str = sm.find("lastmod").text
                lastmod = dateutil.parser.parse(lastmod_str)
                
                # Ensure lastmod is timezone aware for comparison
                if lastmod.tzinfo is None:
                    lastmod = lastmod.replace(tzinfo=dateutil.tz.tzutc())
                
                # Optimization: Skip sitemaps that haven't been modified since start_date
                if lastmod < start_date:
                    logger.debug(f"Skipping sitemap {loc} (Lastmod {lastmod} < {start_date})")
                    continue
                    
                logger.info(f"Scanning sitemap: {loc}")
                try:
                    sm_resp = requests.get(loc, timeout=10)
                    sm_resp.raise_for_status()
                    sm_soup = BeautifulSoup(sm_resp.content, "xml")
                    
                    urls = sm_soup.find_all("url")
                    count_in_sitemap = 0
                    
                    for url_tag in urls:
                        try:
                            news_tag = url_tag.find("news:news")
                            # Archive sitemaps might strictly follow standard sitemap protocol or news extension
                            # BBC archive sitemaps often just have <loc> and <lastmod>, sometimes no <news:news>
                            # If no news tag, we might have to infer date from lastmod or check if there is other metadata
                            
                            pub_date = None
                            title = "Unknown Title"
                            
                            if news_tag:
                                pub_date_str = news_tag.find("news:publication_date").text
                                pub_date = dateutil.parser.parse(pub_date_str)
                                title = news_tag.find("news:title").text
                            
                            # Fallback for archive sitemaps (no news:news tag)
                            if not pub_date and url_tag.find("lastmod"):
                                 pub_date_str = url_tag.find("lastmod").text
                                 pub_date = dateutil.parser.parse(pub_date_str)
                                 
                                 # Try to extract title from URL
                                 link = url_tag.find("loc").text
                                 slug = link.split('/')[-1]
                                 # Basic cleanup of slug
                                 title = slug.replace('-', ' ').title()
                                 # We just guessed the title from the slug, so mark it
                                 is_slug_title = True
                            else:
                                is_slug_title = False

                            if not pub_date:
                                continue

                            # Normalize Timezone
                            if pub_date.tzinfo is None:
                                 pub_date = pub_date.replace(tzinfo=dateutil.tz.tzutc())

                            if start_date <= pub_date <= end_date:
                                link = url_tag.find("loc").text
                                
                                # If title wasn't set by news tag or above logic (should be set above if lastmod exists)
                                if title == "Unknown Title":
                                     slug = link.split('/')[-1]
                                     title = slug.replace('-', ' ').title()
                                     is_slug_title = True
                                
                                found_articles.append({
                                    "url": link,
                                    "title": title,
                                    "published": pub_date.isoformat(),
                                    "source": "BBC News",
                                    "is_slug_title": is_slug_title
                                })
                                count_in_sitemap += 1
                        except Exception as e:
                            continue
                    
                    logger.info(f"  Found {count_in_sitemap} matching articles in {loc}")
                    
                except Exception as e:
                    logger.error(f"Failed to process sitemap {loc}: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to process sitemap index {index_url}: {e}")
        
    return found_articles

def backfill_articles(articles: list[dict], batch_size: int = 10):
    """
    Scrapes content for the articles and archives them.
    """
    aggregator = RSSNewsAggregator(cache_dir="document-cache")
    archive_manager = ArchiveManager()
    
    total = len(articles)
    logger.info(f"Starting backfill for {total} articles...")
    
    batch = []
    processed = 0
    
    for i, meta in enumerate(articles):
        url = meta["url"]
        logger.info(f"[{i+1}/{total}] Scraping: {meta['title']}")
        
        # Check if already in archive to save time (though scraper does this too, we can skip log spam)
        # Actually aggregator._scrape_article_content does the check internally.
        
        # We pass metadata to aggregator so it can cache it
        content = aggregator._scrape_article_content(url, metadata=meta)
        
        if content:
            article_data = meta.copy()
            article_data["content"] = content
            # Ensure consistent keys with what pipeline expects/archive needs
            article_data["link"] = url # Backwards compat
            article_data["summary"] = "" # No summary from sitemap, scraper might generate? No, scraper doesn't gen summary.
            
            batch.append(article_data)
        else:
            logger.warning(f"Failed to scrape content for {url}")
            
        if len(batch) >= batch_size:
            logger.info(f"Archiving batch of {len(batch)} articles...")
            archive_manager.save_articles(batch)
            batch = []
            
        # Be nice to the server
        time.sleep(0.5)
        
    # Final batch
    if batch:
        logger.info(f"Archiving final batch of {len(batch)} articles...")
        archive_manager.save_articles(batch)

def main():
    parser = argparse.ArgumentParser(description="Backfill BBC News from Sitemaps")
    parser.add_argument("--start", default="2025-07-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=datetime.now().strftime("%Y-%m-%d"), help="End date (YYYY-MM-DD)")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of articles to backfill")
    args = parser.parse_args()
    
    # Ensure start/end are timezone aware (UTC) for comparison with sitemap dates
    start_date = dateutil.parser.parse(args.start).replace(tzinfo=dateutil.tz.tzutc())
    end_date = dateutil.parser.parse(args.end).replace(tzinfo=dateutil.tz.tzutc())
    
    # If end_date is at midnight (00:00:00), assume the user meant the end of that day
    if end_date.hour == 0 and end_date.minute == 0 and end_date.second == 0:
        end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    logger.info(f"Searching for articles between {start_date} and {end_date}...")
    
    articles = fetch_sitemap_urls(start_date, end_date, limit=args.limit)
    
    if not articles:
        logger.info("No articles found in that date range.")
        return
        
    logger.info(f"Found {len(articles)} articles in sitemaps.")
    
    if args.limit and len(articles) > args.limit:
        logger.info(f"Limiting to {args.limit} articles as requested.")
        articles = articles[:args.limit]
        
    backfill_articles(articles)
    logger.info("Backfill complete.")

if __name__ == "__main__":
    main()
