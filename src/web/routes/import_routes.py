from flask import Blueprint, render_template, request, flash
from src.web.utils import current_config, event_logger
from src.aggregator.sitemap import SitemapBackfiller
from src.pipeline import IngestionPipeline
import os
import logging

logger = logging.getLogger(__name__)

import_bp = Blueprint("import_routes", __name__)

@import_bp.route("/import", methods=["GET", "POST"])
def import_view():
    cfg = current_config()
    active_backfill = None
    
    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "start_backfill":
            target_month_str = request.form.get("target_month")
            limit = int(request.form.get("limit", 50))
            
            if target_month_str:
                try:
                    year, month = map(int, target_month_str.split("-"))
                    
                    flash(f"Starting backfill for {target_month_str} (Limit: {limit})... this may take a while.", "info")
                    
                    # 1. Discover URLs
                    backfiller = SitemapBackfiller()
                    # We might need to ensure cache dir exists
                    os.makedirs("data", exist_ok=True)
                    
                    urls = backfiller.get_urls_for_month(year, month)
                    total_found = len(urls)
                    
                    if not urls:
                        flash("No articles found for this month in the archive.", "warning")
                    else:
                        # Apply limit
                        urls = urls[:limit]
                        
                        # 2. Process URLs
                        pipeline = IngestionPipeline(cfg["config_path"])
                        stats = {"processed": 0, "imported": 0, "skipped": 0, "errors": 0}
                        
                        for i, url in enumerate(urls):
                            try:
                                # Prepare metadata holder for scraper to fill in title
                                meta_holder = {"is_slug_title": True}
                                
                                # Use pipeline's aggregator to scrape
                                content = pipeline.aggregator._scrape_article_content(url, metadata=meta_holder)
                                
                                if content:
                                    # Use extracted title if available, else fallback to slug
                                    title = meta_holder.get("title")
                                    if not title or meta_holder.get("is_slug_title"):
                                        title = url.split("/")[-1].replace("-", " ").title()
                                    
                                    article_data = {
                                        "title": title,
                                        "link": url,
                                        "published": f"{target_month_str}-01", # Approximate
                                        "content": content,
                                        "source": "BBC Archive",
                                        "is_slug_title": False # We already tried to fix it
                                    }
                                    
                                    # Let's just run process.
                                    result = pipeline.process_article(article_data)
                                    
                                    if result["status"] == "imported":
                                        stats["imported"] += 1
                                    elif result["status"] == "skipped":
                                        stats["skipped"] += 1
                                    else:
                                        stats["errors"] += 1
                                else:
                                    stats["errors"] += 1
                                    
                                stats["processed"] += 1
                                
                            except Exception as e:
                                logger.error(f"Error processing backfill url {url}: {e}")
                                stats["errors"] += 1

                        flash(f"Backfill complete. Found {total_found}. Processed {stats['processed']}. Imported {stats['imported']}. Skipped {stats['skipped']}.", "success")
                        event_logger.log("pipeline", f"Backfill {target_month_str}: {stats['imported']} imported", level="success")
                        
                        active_backfill = {
                            "month": target_month_str,
                            "status": "Completed",
                            "progress": 100
                        }
                        
                except Exception as e:
                    logger.error(f"Backfill error: {e}")
                    flash(f"Backfill failed: {e}", "danger")
            else:
                flash("Please select a month", "warning")

    return render_template(
        "import.html",
        active_page="import_view",
        active_backfill=active_backfill
    )
