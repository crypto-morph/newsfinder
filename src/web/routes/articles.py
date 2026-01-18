from flask import Blueprint, render_template, request, flash, redirect, url_for
from src.web.utils import current_config, get_db, event_logger, build_ollama
from src.archive_manager import ArchiveManager
from src.analysis.verification_service import VerificationService
from src.history import HistoryManager
from src.pipeline import IngestionPipeline
from src.services.tagging import generate_tag_rationale

articles_bp = Blueprint("articles", __name__)

@articles_bp.route("/articles")
def articles_view():
    cfg = current_config()
    db = get_db()
    processed_articles = db.get_all_articles(limit=200) # reasonable limit for view
    
    # Load cached articles from Parquet archive
    archive_mgr = ArchiveManager()
    cached_articles = archive_mgr.get_recent_articles(limit=100)
    
    # Load verifications to merge
    service = VerificationService(cfg)
    recent_verifications = service.get_recent_verifications(limit=500)
    # Create map by URL
    ver_map = {v.get("article_url"): v for v in recent_verifications}
    
    # Load History
    history_mgr = HistoryManager()
    history_map = history_mgr.get_history_map()
    
    # Determine skipped items (in cache but not in processed DB)
    processed_urls = set(a.get("url") for a in processed_articles if a.get("url"))
    skipped_articles = [
        a for a in cached_articles 
        if a.get("url") not in processed_urls
    ]
    
    # Fixup processed articles
    for a in processed_articles:
        # Fix tags (stored as comma-string in DB)
        if isinstance(a.get("topic_tags"), str):
            a["topic_tags"] = [t.strip() for t in a["topic_tags"].split(",") if t.strip()]
        
        # Attach verification
        if a.get("url") in ver_map:
            a["verification"] = ver_map[a["url"]]
        
        # Attach History
        if a.get("id") in history_map:
            a["history"] = history_map[a.get("id")]
            
        # Ensure published date is top level
        if not a.get("published") and a.get("published_date"):
            a["published"] = a["published_date"]
    
    return render_template(
        "articles.html",
        processed=processed_articles,
        skipped=skipped_articles,
        active_page="articles_view"
    )

@articles_bp.route("/articles/<article_id>/status", methods=["POST"])
def update_article_status(article_id: str):
    db = get_db()
    new_status = request.form.get("status")
    if new_status in ["High", "Medium", "Low", "Dismissed"]:
        if db.update_article_metadata(article_id, {"status": new_status}):
            flash(f"Article status updated to {new_status}", "success")
            event_logger.log("edit", f"Updated status for {article_id[:8]}... to {new_status}", level="info")
        else:
            flash("Failed to update status", "danger")
    else:
        flash("Invalid status", "warning")
        
    # Redirect back to where we came from, or default to articles view
    return redirect(request.referrer or url_for("articles.articles_view"))

@articles_bp.route("/articles/<article_id>/reappraise", methods=["POST"])
def reappraise_article(article_id: str):
    cfg = current_config()
    # Initialize pipeline (this is heavy, but necessary for full re-run)
    pipeline = IngestionPipeline(cfg["config_path"])
    
    result = pipeline.reprocess_article(article_id)
    
    if result.get("status") == "imported":
        msg = "Article re-analyzed successfully."
        
        # Add detail about changes
        diff = result.get("history_diff", {})
        if diff:
            changes = []
            if "relevance_score" in diff:
                changes.append(f"Relevance: {diff['relevance_score']['from']} → {diff['relevance_score']['to']}")
            if "impact_score" in diff:
                changes.append(f"Impact: {diff['impact_score']['from']} → {diff['impact_score']['to']}")
            
            if changes:
                msg += " Changes: " + ", ".join(changes)
            else:
                msg += " No score changes."
        else:
            msg += " No significant changes detected."

        flash(msg, "success")
        event_logger.log("pipeline", f"Manually reappraised article {article_id[:8]}...", level="success")
    elif result.get("status") == "error":
        flash(f"Reappraisal failed: {result.get('message')}", "danger")
    else:
        flash(f"Reappraisal skipped: {result.get('reason')}", "warning")
        
    return redirect(request.referrer or url_for("articles.articles_view"))

@articles_bp.route("/articles/<article_id>/tags", methods=["GET", "POST"])
def edit_tags(article_id: str):
    cfg = current_config()
    db = get_db()
    article = db.get_article(article_id)
    if not article:
        flash("Article not found", "warning")
        return redirect(url_for("dashboard.dashboard"))

    if request.method == "POST":
        action = request.form.get("action", "save")
        
        if action == "regenerate":
            ollama = build_ollama(cfg)
            summary_text = article.get("summary_text", "")
            combined_text = f"{article.get('title', '')} {summary_text}".lower()
            new_tags = ollama.extract_topics(combined_text)
            
            if new_tags:
                # Also regenerate rationale since tags changed
                rationale = generate_tag_rationale(
                    ollama, article, new_tags, article.get("key_entities", [])
                )
                
                updated_meta = {
                    "topic_tags": new_tags,
                    "tag_rationale": rationale
                }
                db.update_article_metadata(article_id, updated_meta)
                flash("Tags regenerated with AI", "success")
                event_logger.log("edit", f"Regenerated tags for article {article_id[:8]}...", level="success")
                # Refresh article data
                article = db.get_article(article_id)
            else:
                flash("Could not generate new tags", "warning")
                
        else:  # save action
            topic_text = request.form.get("topic_tags", "")
            entity_text = request.form.get("entity_tags", "")
            topic_tags = [tag.strip() for tag in topic_text.split(",") if tag.strip()]
            entity_tags = [tag.strip() for tag in entity_text.split(",") if tag.strip()]
            updated_meta = {
                "topic_tags": topic_tags,
                "key_entities": entity_tags,
                "tag_rationale": request.form.get("tag_rationale", ""),
            }
            db.update_article_metadata(article_id, updated_meta)
            flash("Tags updated", "success")
            event_logger.log("edit", f"Updated tags for article {article_id[:8]}...", level="info")
            return redirect(url_for("articles.edit_tags", article_id=article_id))

    rationale = article.get("tag_rationale")
    if not rationale:
        ollama = build_ollama(cfg)
        rationale = generate_tag_rationale(
            ollama,
            article,
            article.get("topic_tags", []),
            article.get("key_entities", []),
        )
        if rationale:
            db.update_article_metadata(article_id, {"tag_rationale": rationale})

    return render_template(
        "tag_editor.html",
        article=article,
        rationale=rationale,
        topic_tags=", ".join(article.get("topic_tags", [])),
        entity_tags=", ".join(article.get("key_entities", [])),
        active_page="dashboard",
    )

@articles_bp.route("/articles/<article_id>/delete", methods=["POST"])
def delete_article_route(article_id: str):
    db = get_db()
    if db.delete_article(article_id):
        flash("Article deleted", "success")
        event_logger.log("delete", f"Deleted article {article_id[:8]}...", level="warning")
    else:
        flash("Failed to delete article", "danger")
        event_logger.log("delete", f"Failed to delete article {article_id}", level="error")
    return redirect(url_for("dashboard.dashboard"))
