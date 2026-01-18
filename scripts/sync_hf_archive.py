import os
import requests
import argparse
import logging
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("hf_sync")

BASE_URL = "https://huggingface.co/datasets/RealTimeData/bbc_news_alltime/resolve/main"
ARCHIVE_DIR = "data/archive"

def generate_month_list(start_date: str, end_date: str = None) -> list[str]:
    """Generate a list of YYYY-MM strings between start and end dates."""
    start = datetime.strptime(start_date, "%Y-%m")
    if end_date:
        end = datetime.strptime(end_date, "%Y-%m")
    else:
        end = datetime.now()
    
    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y-%m"))
        # Move to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    return dates

def download_month(month: str, force: bool = False):
    """Download the parquet file for a specific month."""
    # The file structure seems to be consistently train-00000-of-00001.parquet inside the month folder
    remote_url = f"{BASE_URL}/{month}/train-00000-of-00001.parquet"
    local_dir = os.path.join(ARCHIVE_DIR, month)
    local_path = os.path.join(local_dir, "data.parquet")
    
    if os.path.exists(local_path) and not force:
        logger.info(f"Skipping {month}: already exists at {local_path}")
        return

    logger.info(f"Checking {month} at {remote_url}...")
    
    try:
        # Check if exists (HEAD request)
        head = requests.head(remote_url, allow_redirects=True, timeout=10)
        if head.status_code != 200:
            logger.warning(f"Month {month} not found (Status: {head.status_code})")
            return

        # Download
        logger.info(f"Downloading {month}...")
        os.makedirs(local_dir, exist_ok=True)
        
        response = requests.get(remote_url, stream=True, timeout=60)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0
        
        with open(local_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
        
        logger.info(f"Successfully saved to {local_path} ({downloaded/1024/1024:.2f} MB)")
        
    except Exception as e:
        logger.error(f"Failed to download {month}: {e}")

def main():
    parser = argparse.ArgumentParser(description="Sync BBC News parquet files from Hugging Face")
    parser.add_argument("--start", default="2023-01", help="Start month (YYYY-MM)")
    parser.add_argument("--end", help="End month (YYYY-MM), defaults to current month")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    args = parser.parse_args()

    months = generate_month_list(args.start, args.end)
    logger.info(f"Syncing {len(months)} months from {months[0]} to {months[-1]}")
    
    for month in months:
        download_month(month, args.force)

if __name__ == "__main__":
    main()
