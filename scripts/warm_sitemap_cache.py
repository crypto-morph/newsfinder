from src.aggregator.sitemap import SitemapBackfiller
import logging

logging.basicConfig(level=logging.INFO)

print("Pre-building sitemap directory...")
bf = SitemapBackfiller()
bf.build_directory()
print("Done.")
