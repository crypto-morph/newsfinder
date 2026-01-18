import requests
import re
import logging
import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

class SitemapBackfiller:
    def __init__(self, cache_dir: str = "data"):
        self.index_url = "https://www.bbc.co.uk/sitemaps/https-index-uk-archive.xml"
        self.cache_dir = cache_dir
        self.index_cache_file = os.path.join(cache_dir, "sitemap_directory.json")
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    def _fetch_xml(self, url: str) -> Optional[BeautifulSoup]:
        try:
            response = requests.get(url, headers=self.headers, timeout=20)
            response.raise_for_status()
            return BeautifulSoup(response.content, "xml")
        except Exception as e:
            logger.error(f"Failed to fetch XML from {url}: {e}")
            return None

    def build_directory(self, force: bool = False) -> List[Dict]:
        """
        Scans the main archive index and determines the date range for each sub-sitemap.
        Returns a list of dicts: {'url': str, 'start': str, 'end': str}
        """
        if not force and os.path.exists(self.index_cache_file):
            try:
                with open(self.index_cache_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass

        logger.info("Building sitemap directory (this may take a while)...")
        soup = self._fetch_xml(self.index_url)
        if not soup:
            return []

        sitemaps = soup.find_all("sitemap")
        directory = []

        for sm in sitemaps:
            loc = sm.find("loc").text
            logger.info(f"Inspecting sitemap: {loc}")
            
            sub_soup = self._fetch_xml(loc)
            if not sub_soup:
                continue

            urls = sub_soup.find_all("url")
            if not urls:
                continue

            # Find dates in first and last entries
            start_date = self._extract_date(urls[0])
            end_date = self._extract_date(urls[-1])

            if start_date and end_date:
                entry = {
                    "url": loc,
                    "start": start_date,
                    "end": end_date,
                    "count": len(urls)
                }
                directory.append(entry)
                # Save progress incrementally
                self._save_directory(directory)

        return directory

    def _extract_date(self, url_tag) -> Optional[str]:
        # Try lastmod first
        lastmod = url_tag.find("lastmod")
        if lastmod:
            return lastmod.text[:10]  # YYYY-MM-DD
        
        # Fallback to URL regex
        loc = url_tag.find("loc").text
        match = re.search(r'/(\d{4})/(\d{2})/', loc) # /YYYY/MM/ pattern?
        # BBC URLs often don't have dates in path for older content, but let's try
        # Actually BBC URLs vary a lot. 
        # But looking at explore_sitemap output, lastmod seems reliable for the archive sitemaps.
        return None

    def _save_directory(self, directory: List[Dict]):
        os.makedirs(self.cache_dir, exist_ok=True)
        with open(self.index_cache_file, "w") as f:
            json.dump(directory, f, indent=2)

    def get_urls_for_month(self, year: int, month: int) -> List[str]:
        """
        Finds all article URLs in the archives that match the given month.
        """
        target_prefix = f"{year}-{month:02d}"
        directory = self.build_directory()
        
        relevant_sitemaps = []
        for entry in directory:
            # Check overlap
            # Start of sitemap <= End of target month
            # End of sitemap >= Start of target month
            # Simple string comparison works for ISO dates
            s_start = entry.get("start", "")
            s_end = entry.get("end", "")
            
            # Target range
            t_start = f"{target_prefix}-01"
            # distinct end of month is hard without cal lib, but string prefix check is enough for inclusion?
            # Actually, just checking if the sitemap range *contains* any dates from the month.
            # Ideally: sitemap_start <= month_end AND sitemap_end >= month_start
            
            if s_start <= f"{target_prefix}-31" and s_end >= f"{target_prefix}-01":
                relevant_sitemaps.append(entry["url"])

        logger.info(f"Found {len(relevant_sitemaps)} relevant sitemaps for {target_prefix}")
        
        found_urls = []
        for sm_url in relevant_sitemaps:
            logger.info(f"Scanning {sm_url}...")
            soup = self._fetch_xml(sm_url)
            if not soup:
                continue
                
            for url_tag in soup.find_all("url"):
                lastmod = url_tag.find("lastmod")
                if lastmod and lastmod.text.startswith(target_prefix):
                    loc = url_tag.find("loc").text
                    found_urls.append(loc)
        
        return found_urls
