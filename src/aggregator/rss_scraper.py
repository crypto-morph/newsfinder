import feedparser
import requests
from bs4 import BeautifulSoup
from typing import Any, List, Dict, Optional
import logging
import time
import os
import json
import hashlib

logger = logging.getLogger(__name__)

class RSSNewsAggregator:
    def __init__(self, feed_urls: Optional[List] = None, cache_dir: Optional[str] = None):
        self.feed_urls = feed_urls or []
        self.cache_dir = cache_dir
        if self.cache_dir:
            os.makedirs(self.cache_dir, exist_ok=True)

    def _fetch_feed(self, feed_url: str) -> tuple[Optional[feedparser.FeedParserDict], str]:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (NewsFinder Preview)"
            }
            response = requests.get(feed_url, headers=headers, timeout=10)
            response.raise_for_status()
        except Exception as exc:
            return None, str(exc)

        return feedparser.parse(response.content), ""

    def _get_cache_path(self, url: str) -> Optional[str]:
        if not self.cache_dir:
            return None
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return os.path.join(self.cache_dir, f"{url_hash}.json")

    def fetch_recent_articles(self, limit_per_feed: int = 3, skip_callback: Optional[callable] = None) -> List[Dict]:
        """
        Fetches recent articles from all configured RSS feeds.
        
        Args:
            limit_per_feed: Max number of articles to fetch per feed.
            skip_callback: Optional function(url) -> bool. If True, article is skipped (not scraped).
        """
        all_articles = []
        
        for feed in self.feed_urls:
            try:
                feed_url = feed.get("url") if isinstance(feed, dict) else feed
                feed_name = feed.get("name") if isinstance(feed, dict) else None
                if not feed_url:
                    continue

                logger.info(f"Fetching RSS feed from {feed_url}")
                parsed_feed, error = self._fetch_feed(feed_url)
                if not parsed_feed:
                    raise RuntimeError(error or "Failed to fetch feed")
                
                # Determine source from feed title or URL
                source_name = feed_name or parsed_feed.feed.get('title', feed_url)
                
                for entry in parsed_feed.entries[:limit_per_feed]:
                    # Check if we should skip this article before scraping
                    if skip_callback and skip_callback(entry.link):
                        logger.debug(f"Skipping known article: {entry.title}")
                        continue

                    content = self._scrape_article_content(entry.link)
                    if not content:
                        continue
                        
                    article = {
                        "title": entry.title,
                        "link": entry.link,
                        "published": entry.get('published', time.strftime("%a, %d %b %Y %H:%M:%S +0000")), # Fallback time
                        "summary": self._clean_summary(entry.get("summary", "")),
                        "content": content,
                        "source": source_name
                    }
                    all_articles.append(article)
                    logger.info(f"Processed article: {entry.title} from {source_name}")
            
            except Exception as e:
                logger.error(f"Error fetching feed {feed}: {e}")
                
        return all_articles

    def fetch_feed_preview(self, limit_per_feed: int = 3) -> Dict[str, Any]:
        """Fetch lightweight preview data without scraping article content."""
        previews = []
        errors: List[str] = []
        warnings: List[str] = []
        for feed in self.feed_urls:
            try:
                feed_url = feed.get("url") if isinstance(feed, dict) else feed
                feed_name = feed.get("name") if isinstance(feed, dict) else None
                if not feed_url:
                    continue

                logger.info("Previewing RSS feed from %s", feed_url)
                parsed_feed, error = self._fetch_feed(feed_url)
                if not parsed_feed:
                    errors.append(f"{feed_name or feed_url}: {error}")
                    continue
                source_name = feed_name or parsed_feed.feed.get("title", feed_url)

                if getattr(parsed_feed, "bozo", False):
                    error = getattr(parsed_feed, "bozo_exception", None)
                    errors.append(
                        f"{source_name}: {error or 'Failed to parse feed'}"
                    )

                if not parsed_feed.entries:
                    warnings.append(f"{source_name}: no entries returned")

                for entry in parsed_feed.entries[:limit_per_feed]:
                    previews.append(
                        {
                            "title": entry.title,
                            "link": entry.link,
                            "published": entry.get(
                                "published",
                                time.strftime("%a, %d %b %Y %H:%M:%S +0000"),
                            ),
                            "summary": self._clean_summary(entry.get("summary", "")),
                            "source": source_name,
                        }
                    )
            except Exception as e:
                logger.error("Error previewing feed %s: %s", feed, e)
                errors.append(f"{feed}: {e}")

        return {"articles": previews, "errors": errors, "warnings": warnings}

    def _clean_summary(self, text: str) -> str:
        if not text:
            return ""
        try:
            soup = BeautifulSoup(text, "html.parser")
            clean_text = soup.get_text(separator=" ", strip=True)
            # Remove common "Continue reading..." suffix
            clean_text = clean_text.replace("Continue reading...", "")
            return clean_text.strip()
        except Exception:
            return text

    def _scrape_article_content(self, url: str) -> str:
        """
        Scrapes the main text content from a news article URL.
        Includes heuristics for common UK news sites.
        """
        # Check cache first
        cache_path = self._get_cache_path(url)
        if cache_path and os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Simple expiry check (optional, let's say 30 days)
                    if time.time() - data.get("timestamp", 0) < 30 * 86400:
                        logger.debug(f"Cache hit for {url}")
                        return data.get("content", "")
            except Exception as e:
                logger.warning(f"Failed to read cache for {url}: {e}")

        try:
            # Add a generic User-Agent to avoid 403s
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove scripts and styles
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()

            # Heuristics for content extraction
            text_blocks = []
            
            # 1. BBC Specific
            if "bbc.co" in url:
                text_blocks = soup.find_all("div", {"data-component": "text-block"})
            
            # 2. Guardian Specific
            elif "theguardian.com" in url:
                article_body = soup.find("div", {"class": "article-body-commercial-selector"}) or soup.find("div", {"data-gu-name": "body"})
                if article_body:
                    text_blocks = article_body.find_all("p")

            # 3. Telegraph Specific (Often paywalled/complex, but try standard article body)
            elif "telegraph.co.uk" in url:
                 text_blocks = soup.find_all("div", {"data-test": "article-body-text"})

            # 4. Generic Fallback: Find all paragraphs
            if not text_blocks:
                # Try to find the element with the most <p> tags
                # This is a crude "readability" heuristic
                text_blocks = soup.find_all("p")
            
            # Clean and join
            article_text = " ".join([block.get_text().strip() for block in text_blocks])
            
            # Filter out very short content (likely errors or just cookie warnings)
            if len(article_text) < 200:
                return ""
            
            # Save to cache
            if cache_path:
                try:
                    with open(cache_path, "w", encoding="utf-8") as f:
                        json.dump({
                            "url": url,
                            "timestamp": time.time(),
                            "content": article_text
                        }, f)
                except Exception as e:
                    logger.warning(f"Failed to write cache for {url}: {e}")
                
            return article_text

        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return ""
