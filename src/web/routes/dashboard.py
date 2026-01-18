from flask import Blueprint, render_template, request, flash, redirect, url_for
from src.web.utils import (
    current_config, get_db, load_status, load_alerts, 
    enrich_context, load_context, build_ollama, event_logger
)
from src.services.tagging import match_goals, derive_topic_tags
from src.feedback import get_bad_tags, filter_tags, append_feedback

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/")
def dashboard():
    cfg = current_config()
    status = load_status(cfg["storage"]["status_file"])
    alerts = load_alerts(cfg["storage"]["alerts_log"])
    db = get_db()
    total_articles = db.get_stats()
    articles = db.list_recent_articles(limit=10)
    context = enrich_context(load_context(cfg["storage"]["context_cache"]), cfg)

    if not status.get("last_run") or status.get("last_run") == "—":
        status["last_run"] = "Not recorded (run pipeline)"
    if status.get("articles_processed", 0) == 0 and total_articles:
        status["articles_processed"] = total_articles

    # Use primary company for dashboard goals/keywords
    primary_ctx = context.get("structured", {}).get("companies", [{}])[0]
    goals = primary_ctx.get("business_goals", [])
    focus_keywords = primary_ctx.get("focus_keywords", [])
    
    relevance_cutoff = (
        cfg.get("pipeline", {})
        .get("alert_threshold", {})
        .get("relevance", 7)
    )

    ollama = None
    feedback_log = cfg["storage"]["feedback_log"]
    bad_tags = get_bad_tags(feedback_log)

    for article in articles:
        # Fix list fields that might be strings
        if isinstance(article.get("key_entities"), str):
            article["key_entities"] = [k.strip() for k in article["key_entities"].split(",") if k.strip()]
        
        if isinstance(article.get("topic_tags"), str):
            article["topic_tags"] = [t.strip() for t in article["topic_tags"].split(",") if t.strip()]

        # Ensure published date is consistent
        if not article.get("published") and article.get("published_date"):
            article["published"] = article["published_date"]

        summary_text = article.get("summary_text", "")
        combined_text = f"{article.get('title', '')} {summary_text}".lower()
        article["entity_tags"] = article.get("key_entities") or []
        article["goal_matches"] = match_goals(combined_text, goals)
        article["keyword_matches"] = [
            kw for kw in focus_keywords if kw.lower() in combined_text
        ]
        if not article.get("topic_tags"):
            if ollama is None:
                ollama = build_ollama(cfg)
            new_tags = ollama.extract_topics(combined_text)
            if new_tags:
                db.update_article_metadata(article["id"], {"topic_tags": new_tags})
                article["topic_tags"] = new_tags
        article["topic_tags"] = filter_tags(
            derive_topic_tags(article, article["keyword_matches"]),
            bad_tags,
        )
        article["company_match"] = (
            (article.get("relevance_score") or 0) >= relevance_cutoff
        )

    company_filter = request.args.get("company")
    goal_filter = request.args.get("goal")
    if company_filter:
        articles = [article for article in articles if article.get("company_match")]
    if goal_filter:
        articles = [
            article
            for article in articles
            if goal_filter in article.get("goal_matches", [])
        ]

    return render_template(
        "dashboard.html",
        status=status,
        alerts=alerts,
        articles=articles,
        context=context,
        total_articles=total_articles,
        active_page="dashboard",
        company_filter=bool(company_filter),
        goal_filter=goal_filter,
        available_goals=goals,
    )

@dashboard_bp.route("/tag-feedback", methods=["POST"])
def tag_feedback():
    cfg = current_config()
    tag = request.form.get("tag", "").strip()
    reason = request.form.get("reason", "").strip()
    article_id = request.form.get("article_id", "").strip()
    if tag:
        append_feedback(
            cfg["storage"]["feedback_log"],
            {
                "tag": tag,
                "reason": reason,
                "article_id": article_id,
                "verdict": "bad",
            },
        )
        flash("Tag feedback recorded", "success")
        event_logger.log("feedback", f"Tag feedback: '{tag}' marked as bad", level="info")
    else:
        flash("No tag provided", "warning")
    
    if article_id:
        return redirect(url_for("articles.edit_tags", article_id=article_id))
    return redirect(url_for("dashboard.dashboard"))
