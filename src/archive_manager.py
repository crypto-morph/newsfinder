import os
import glob
import logging
import pandas as pd
from typing import Optional, Dict, List
from datetime import datetime
import dateutil.parser

logger = logging.getLogger(__name__)

class ArchiveManager:
    def __init__(self, archive_dir: str = "data/archive"):
        self.archive_dir = archive_dir
        self._cache = {}  # Map month_str -> DataFrame

    def _get_month_path(self, month_str: str) -> List[str]:
        """Get all parquet files for a given month."""
        month_dir = os.path.join(self.archive_dir, month_str)
        if not os.path.exists(month_dir):
            return []
        return glob.glob(os.path.join(month_dir, "*.parquet"))

    def _load_month(self, month_str: str) -> Optional[pd.DataFrame]:
        """Load DataFrame for a month, using memory cache."""
        if month_str in self._cache:
            return self._cache[month_str]
        
        files = self._get_month_path(month_str)
        if not files:
            return None
        
        dfs = []
        for f in files:
            try:
                df = pd.read_parquet(f)
                # Normalize columns: HF has 'link', we use 'url'
                if 'link' in df.columns and 'url' not in df.columns:
                    df = df.rename(columns={'link': 'url'})
                dfs.append(df)
            except Exception as e:
                logger.error(f"Error reading {f}: {e}")
        
        if not dfs:
            return None
            
        try:
            combined = pd.concat(dfs, ignore_index=True)
            # Create index on url for faster lookups
            if 'url' in combined.columns:
                combined = combined.set_index('url', drop=False)
            self._cache[month_str] = combined
            return combined
        except Exception as e:
            logger.error(f"Error combining dataframes for {month_str}: {e}")
            return None

    def get_article(self, url: str, published_date_str: Optional[str] = None) -> Optional[Dict]:
        """
        Try to find article in archive.
        If date is provided, look in that month.
        """
        months_to_check = []
        if published_date_str:
            try:
                dt = dateutil.parser.parse(published_date_str)
                months_to_check.append(dt.strftime("%Y-%m"))
            except Exception:
                pass
        
        # If parsing failed or no date, maybe check current and previous month? 
        # For now, if no date, we can't efficiently search partitioned archive.
        if not months_to_check:
            # Fallback: check current month
            months_to_check.append(datetime.now().strftime("%Y-%m"))

        for month in months_to_check:
            df = self._load_month(month)
            if df is not None:
                if url in df.index:
                    # Found it
                    row = df.loc[url]
                    # Handle duplicates (if multiple rows have same URL)
                    if isinstance(row, pd.DataFrame):
                        row = row.iloc[0]
                    return row.to_dict()
        
        return None

    def get_recent_articles(self, limit: int = 100) -> List[Dict]:
        """
        Get recently archived articles across recent months.
        Useful for replacing the JSON cache listing.
        """
        months = sorted(glob.glob(os.path.join(self.archive_dir, "*")), reverse=True)
        articles = []
        
        for month_path in months:
            if not os.path.isdir(month_path):
                continue
            
            month_str = os.path.basename(month_path)
            df = self._load_month(month_str)
            if df is None or df.empty:
                continue
                
            # Convert timestamp/published to comparable
            # We'll just take the tail since we append new stuff
            # But duplicate handling keeps 'last', so tail is recent.
            
            # Convert to list of dicts, reverse to get newest first
            batch = df.tail(limit - len(articles)).to_dict('records')
            # Reverse to show newest first
            articles.extend(reversed(batch))
            
            if len(articles) >= limit:
                break
                
        return articles[:limit]

    def save_articles(self, articles: List[Dict]):
        """
        Save a list of articles to local.parquet in appropriate month folders.
        Batches writes by month.
        """
        by_month = {}
        for art in articles:
            # Normalize link -> url
            if "link" in art and "url" not in art:
                art["url"] = art["link"]
                # Optional: keep or remove 'link'? Let's keep 'link' for compatibility if needed, 
                # but 'url' is our primary key for index.
            
            # Parse date
            date_str = art.get("published")
            month_str = datetime.now().strftime("%Y-%m") # Default
            if date_str:
                try:
                    dt = dateutil.parser.parse(date_str)
                    month_str = dt.strftime("%Y-%m")
                except:
                    pass
            
            if month_str not in by_month:
                by_month[month_str] = []
            by_month[month_str].append(art)
        
        # Write partitions
        for month_str, arts in by_month.items():
            month_dir = os.path.join(self.archive_dir, month_str)
            os.makedirs(month_dir, exist_ok=True)
            local_path = os.path.join(month_dir, "local.parquet")
            
            # Convert to DF
            new_df = pd.DataFrame(arts)
            # Ensure 'url' is present (should be done above)
            
            # Check if exists to append
            if os.path.exists(local_path):
                try:
                    existing_df = pd.read_parquet(local_path)
                    combined_df = pd.concat([existing_df, new_df]).drop_duplicates(subset=['url'], keep='last')
                    combined_df.to_parquet(local_path)
                except Exception as e:
                    logger.error(f"Failed to update {local_path}: {e}")
            else:
                new_df.to_parquet(local_path)
            
            # Invalidate cache
            if month_str in self._cache:
                del self._cache[month_str]
