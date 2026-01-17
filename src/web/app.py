"""Flask application providing the News Finder dashboard."""

from __future__ import annotations

import json
import os
import copy
import re
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

from flask import (
    Flask,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
    jsonify,
)

import yaml

from src.aggregator.rss_scraper import RSSNewsAggregator
from src.analysis.llm_client import OllamaClient
from src.context_profiler import CompanyContextProfiler
from src.database.chroma_client import NewsDatabase
from src.feedback import append_feedback, filter_tags, get_bad_tags
from src.pipeline import IngestionPipeline
from src.settings import load_config
from src.web.logging_service import EventLogger

import logging

logger = logging.getLogger(__name__)

# Global event logger
event_logger = EventLogger()

NAV_LINKS = [
    {"label": "Dashboard", "endpoint": "dashboard", "icon": "mdi-view-dashboard"},
    {"label": "Articles", "endpoint": "articles_view", "icon": "mdi-file-document-multiple-outline"},
    {"label": "RAG Explorer", "endpoint": "explore", "icon": "mdi-magnify"},
    {"label": "Discovery", "endpoint": "discovery", "icon": "mdi-compass-outline"},
    {"label": "Sources", "endpoint": "sources", "icon": "mdi-rss"},
    {"label": "Config & Context", "endpoint": "config_view", "icon": "mdi-cog-outline"},
]

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "into",
    "that",
    "this",
    "their",
    "your",
    "about",
    "across",
    "through",
    "over",
    "under",
    "health",
    "wellness",
    "services",
    "service",
    "business",
}


def create_app(config_path: str = "config.yaml") -> Flask:
    template_dir = Path(__file__).parent / "templates"
    app = Flask(__name__, template_folder=str(template_dir))
    app.config["NEWSFINDER_CONFIG"] = load_config(config_path)
    app.config["SECRET_KEY"] = os.environ.get("NEWSFINDER_SECRET", "newsfinder")
    app.config["NAV_LINKS"] = NAV_LINKS

    register_routes(app)
    register_teardown(app)

    @app.context_processor
    def inject_globals():  # type: ignore[func-returns-value]
        return {
            "app_name": "News Finder",
            "nav_links": app.config.get("NAV_LINKS", []),
        }

    return app


def load_cached_articles(cache_dir: str = "document-cache") -> List[Dict[str, Any]]:
    if not os.path.exists(cache_dir):
        return []
    
    cached = []
    try:
        for filename in os.listdir(cache_dir):
            if filename.endswith(".json"):
                filepath = os.path.join(cache_dir, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        # We only need metadata for the list
                        cached.append({
                            "url": data.get("url"),
                            "title": data.get("title", "Unknown Title"),
                            "source": data.get("source", "Unknown Source"),
                            "published": data.get("published", ""),
                            "summary": data.get("summary", ""),
                            "timestamp": data.get("timestamp", 0)
                        })
                except Exception as e:
                    logger.warning(f"Failed to load cache file {filename}: {e}")
    except Exception as e:
        logger.error(f"Error reading cache dir: {e}")
        
    # Sort by timestamp desc
    cached.sort(key=lambda x: x["timestamp"], reverse=True)
    return cached


def register_routes(app: Flask) -> None:
    @app.route("/")
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

    @app.route("/articles")
    def articles_view():
        db = get_db()
        processed_articles = db.get_all_articles(limit=200) # reasonable limit for view
        cached_articles = load_cached_articles()
        
        # Determine skipped items (in cache but not in processed DB)
        processed_urls = set(a.get("url") for a in processed_articles if a.get("url"))
        skipped_articles = [
            a for a in cached_articles 
            if a.get("url") not in processed_urls
        ]
        
        return render_template(
            "articles.html",
            processed=processed_articles,
            skipped=skipped_articles,
            active_page="articles_view"
        )

    @app.route("/explore")
    def explore():
        cfg = current_config()
        query = request.args.get("q", "").strip()
        results: List[Dict[str, Any]] = []

        if query:
            ollama = build_ollama(cfg)
            embedding = ollama.generate_embedding(query)
            if embedding:
                raw = get_db().query_articles(embedding, n_results=5)
                ids = raw.get("ids", [[]])[0]
                docs = raw.get("documents", [[]])[0]
                metas = raw.get("metadatas", [[]])[0]
                distances = raw.get("distances", [[]])[0]
                for idx, item_id in enumerate(ids):
                    summary = docs[idx] if idx < len(docs) else ""
                    metadata = metas[idx] if idx < len(metas) else {}
                    score = distances[idx] if idx < len(distances) else None
                    results.append(
                        {
                            "id": item_id,
                            "summary": summary,
                            "metadata": metadata,
                            "score": score,
                        }
                    )

        return render_template(
            "explore.html",
            query=query,
            results=results,
            active_page="explore",
        )

    @app.route("/discovery", methods=["GET", "POST"])
    def discovery():
        cfg = current_config()
        
        if request.method == "POST":
            new_keyword = request.form.get("new_keyword", "").strip()
            if new_keyword:
                keywords = cfg.get("pipeline", {}).get("keywords", [])
                if new_keyword.lower() not in [k.lower() for k in keywords]:
                    keywords.append(new_keyword)
                    updated = copy.deepcopy(cfg)
                    updated.setdefault("pipeline", {})["keywords"] = keywords
                    save_config(updated)
                    flash(f"Added keyword: {new_keyword}", "success")
                else:
                    flash(f"Keyword '{new_keyword}' already exists", "warning")
            return redirect(url_for("discovery"))

        feeds = cfg.get("feeds", [])
        # Fetch a sample for discovery
        aggregator = RSSNewsAggregator(feed_urls=feeds)
        raw_articles = aggregator.fetch_recent_articles(limit_per_feed=5)
        
        keywords = set(k.lower() for k in cfg.get("pipeline", {}).get("keywords", []))
        
        discovery_items = []
        for article in raw_articles:
            # Check match against full content (like pipeline) but also title/summary for display
            text_to_check = (article["title"] + " " + article["content"]).lower()
            matched_keywords = [k for k in keywords if k in text_to_check]
            
            discovery_items.append({
                "title": article["title"],
                "url": article["link"],
                "source": article["source"],
                "published": article["published"],
                "summary": article["summary"], 
                "matches": matched_keywords,
                "is_match": bool(matched_keywords)
            })
            
        return render_template(
            "discovery.html",
            articles=discovery_items,
            current_keywords=sorted(list(keywords)),
            active_page="discovery"
        )

    @app.route("/config", methods=["GET", "POST"])
    def config_view():
        cfg = current_config()
        # Ensure context is loaded and enriched with company list
        context = enrich_context(load_context(cfg["storage"]["context_cache"]), cfg)
        config_data = copy.deepcopy(cfg)
        keywords_text = ", ".join(config_data.get("pipeline", {}).get("keywords", []))
        config_json = json.dumps(config_data, indent=2, ensure_ascii=False)

        if request.method == "POST":
            action = request.form.get("action")
            
            if action == "refresh_context":
                index = int(request.form.get("index", 0))
                profiler = CompanyContextProfiler(cfg["config_path"])
                try:
                    profiler.refresh_context(index)
                    flash(f"Context refreshed for company #{index+1}", "success")
                    event_logger.log("config", f"Context refreshed for company #{index+1}", level="success")
                except Exception as e:
                    flash(f"Failed to refresh context: {e}", "danger")
                    event_logger.log("config", f"Failed to refresh context: {e}", level="error")
            
            elif action == "refresh_all_contexts":
                profiler = CompanyContextProfiler(cfg["config_path"])
                profiler.refresh_all_contexts()
                flash("All company contexts refreshed", "success")
                event_logger.log("config", "All company contexts refreshed", level="success")

            elif action == "add_company":
                new_name = request.form.get("new_name", "").strip()
                new_url = request.form.get("new_url", "").strip()
                if new_url:
                    companies = cfg.get("companies", [])
                    companies.append({"name": new_name or "New Company", "url": new_url})
                    updated = copy.deepcopy(cfg)
                    updated["companies"] = companies
                    save_config(updated)
                    flash("Company added", "success")
                    event_logger.log("config", f"Added company: {new_name} ({new_url})", level="info")
                else:
                    flash("Company URL is required", "warning")

            elif action == "remove_company":
                try:
                    index = int(request.form.get("index", -1))
                    companies = cfg.get("companies", [])
                    if 0 <= index < len(companies):
                        removed = companies.pop(index)
                        updated = copy.deepcopy(cfg)
                        updated["companies"] = companies
                        save_config(updated)
                        flash(f"Removed company: {removed.get('name')}", "success")
                        event_logger.log("config", f"Removed company: {removed.get('name')}", level="warning")
                    else:
                        flash("Invalid company selected", "warning")
                except ValueError:
                    flash("Invalid index", "warning")

            elif action == "save_company":
                try:
                    index = int(request.form.get("index", -1))
                    name = request.form.get("name", "").strip()
                    url = request.form.get("url", "").strip()
                    companies = cfg.get("companies", [])
                    
                    if 0 <= index < len(companies) and url:
                        companies[index] = {"name": name, "url": url}
                        updated = copy.deepcopy(cfg)
                        updated["companies"] = companies
                        save_config(updated)
                        flash("Company updated", "success")
                        event_logger.log("config", f"Updated company: {name}", level="info")
                    else:
                        flash("Invalid data or company selected", "warning")
                except ValueError:
                    flash("Invalid index", "warning")

            elif action == "generate_keywords":
                profiler = CompanyContextProfiler(cfg["config_path"])
                new_keywords = profiler.generate_broad_keywords()
                if new_keywords:
                    updated = copy.deepcopy(cfg)
                    # Merge with existing, keeping unique
                    existing = set(updated.get("pipeline", {}).get("keywords", []))
                    existing.update(new_keywords)
                    updated.setdefault("pipeline", {})["keywords"] = sorted(list(existing))
                    save_config(updated)
                    flash(f"Generated {len(new_keywords)} new keywords", "success")
                    event_logger.log("config", f"Generated {len(new_keywords)} new keywords with AI", level="success")
                else:
                    flash("Failed to generate keywords", "warning")

            elif action == "add_keyword":
                new_kw = request.form.get("keyword", "").strip()
                if new_kw:
                    keywords = cfg.get("pipeline", {}).get("keywords", [])
                    # Case-insensitive check
                    if new_kw.lower() not in [k.lower() for k in keywords]:
                        keywords.append(new_kw)
                        keywords.sort()
                        updated = copy.deepcopy(cfg)
                        updated.setdefault("pipeline", {})["keywords"] = keywords
                        save_config(updated)
                        flash(f"Added keyword: {new_kw}", "success")
                        event_logger.log("config", f"Added keyword: {new_kw}", level="info")
                    else:
                        flash(f"Keyword '{new_kw}' already exists", "warning")
            
            elif action == "remove_keyword":
                kw_to_remove = request.form.get("keyword", "")
                keywords = cfg.get("pipeline", {}).get("keywords", [])
                if kw_to_remove in keywords:
                    keywords.remove(kw_to_remove)
                    updated = copy.deepcopy(cfg)
                    updated.setdefault("pipeline", {})["keywords"] = keywords
                    save_config(updated)
                    flash(f"Removed keyword: {kw_to_remove}", "success")
                    event_logger.log("config", f"Removed keyword: {kw_to_remove}", level="info")

            elif action == "save_profile_manual":
                try:
                    index = int(request.form.get("index", -1))
                    profiler = CompanyContextProfiler(cfg["config_path"])
                    # Access internal method to get mutable objects
                    contexts = profiler._load_persisted_contexts()
                    
                    if 0 <= index < len(contexts):
                        ctx = contexts[index]
                        ctx.offer_summary = request.form.get("offer_summary", "").strip()
                        ctx.market_position = request.form.get("market_position", "").strip()
                        
                        goals_text = request.form.get("business_goals", "")
                        ctx.business_goals = [line.strip() for line in goals_text.splitlines() if line.strip()]
                        
                        products_text = request.form.get("key_products", "")
                        ctx.key_products = [line.strip() for line in products_text.splitlines() if line.strip()]
                        
                        keywords_text = request.form.get("focus_keywords", "")
                        ctx.focus_keywords = [k.strip() for k in keywords_text.split(",") if k.strip()]
                        
                        profiler._persist_contexts(contexts)
                        flash(f"Profile for {ctx.company_name} updated manually", "success")
                        event_logger.log("config", f"Profile for {ctx.company_name} updated manually", level="info")
                    else:
                        flash("Invalid profile index", "warning")
                except ValueError:
                    flash("Invalid index", "warning")
                except Exception as e:
                    logger.error(f"Error saving profile: {e}")
                    flash(f"Error saving profile: {e}", "danger")

            return redirect(url_for("config_view"))

        return render_template(
            "config.html",
            config=config_data,
            context=context,
            config_json=config_json,
            keywords_text=keywords_text,
            active_page="config",
        )

    @app.route("/sources", methods=["GET", "POST"])
    def sources():
        cfg = current_config()
        feeds = list(cfg.get("feeds", []))
        preview: List[Dict[str, Any]] = []
        selected_index = request.args.get("index", "0")
        try:
            selected_index = int(selected_index)
        except ValueError:
            selected_index = 0
        if selected_index < 0:
            selected_index = 0
        if selected_index >= len(feeds) and feeds:
            selected_index = len(feeds) - 1

        if request.method == "POST":
            action = request.form.get("action")
            selected_index = int(request.form.get("index", selected_index))
            logger.info(f"Sources route POST: action={action}, index={selected_index}")

            if action == "add_source":
                new_feed = request.form.get("new_feed", "").strip()
                new_name = request.form.get("new_name", "").strip()
                if new_feed:
                    feeds.append({"name": new_name or "New Source", "url": new_feed})
                    selected_index = len(feeds) - 1
                    updated = copy.deepcopy(cfg)
                    updated["feeds"] = feeds
                    save_config(updated)
                    flash("Source added", "success")
                    event_logger.log("config", f"Added source: {new_name} ({new_feed})", level="info")
                else:
                    flash("Please provide a feed URL", "warning")
            elif action == "save_source":
                feed_url = request.form.get("feed_url", "").strip()
                feed_name = request.form.get("feed_name", "").strip()
                if 0 <= selected_index < len(feeds) and feed_url:
                    feeds[selected_index] = {
                        "name": feed_name or feeds[selected_index].get("name", "Source"),
                        "url": feed_url,
                    }
                    updated = copy.deepcopy(cfg)
                    updated["feeds"] = feeds
                    save_config(updated)
                    flash("Source updated", "success")
                    event_logger.log("config", f"Updated source: {feed_name}", level="info")
                else:
                    flash("No source selected", "warning")
            elif action == "remove_source":
                if 0 <= selected_index < len(feeds):
                    removed = feeds.pop(selected_index)
                    updated = copy.deepcopy(cfg)
                    updated["feeds"] = feeds
                    save_config(updated)
                    flash(f"Removed source: {removed.get('name', 'source')}", "success")
                    event_logger.log("config", f"Removed source: {removed.get('name', 'source')}", level="warning")
                    if selected_index >= len(feeds):
                        selected_index = max(len(feeds) - 1, 0)
                else:
                    flash("No source selected", "warning")
            elif action == "preview_source":
                logger.info(f"Preview source requested for index {selected_index}")
                if 0 <= selected_index < len(feeds):
                    logger.info(f"Fetching preview for feed: {feeds[selected_index]}")
                    aggregator = RSSNewsAggregator(feed_urls=[feeds[selected_index]])
                    preview_result = aggregator.fetch_feed_preview(
                        limit_per_feed=cfg.get("pipeline", {}).get("articles_per_feed", 3)
                    )
                    preview = preview_result.get("articles", [])
                    errors = preview_result.get("errors", [])
                    warnings = preview_result.get("warnings", [])
                    logger.info(f"Preview result: {len(preview)} articles, {len(errors)} errors, {len(warnings)} warnings")

                    name = feeds[selected_index].get("name", "source")
                    if errors:
                        msg = "Preview error: " + " | ".join(errors)
                        logger.error(msg)
                        flash(msg, "danger")
                    if warnings:
                        msg = "Preview warning: " + " | ".join(warnings)
                        logger.warning(msg)
                        flash(msg, "warning")
                    if preview:
                        flash(f"Previewed {len(preview)} articles from {name}", "info")
                    elif not errors:
                        logger.warning(f"No preview results and no errors for {name}")
                        flash(f"No preview results from {name}", "warning")
                else:
                    logger.warning(f"Invalid source selected: {selected_index}")
                    flash("No source selected", "warning")

        selected_feed = feeds[selected_index] if feeds else {"name": "", "url": ""}
        return render_template(
            "sources.html",
            feeds=feeds,
            selected_index=selected_index,
            selected_feed=selected_feed,
            preview=preview,
            active_page="sources",
        )

    @app.route("/articles/<article_id>/tags", methods=["GET", "POST"])
    def edit_tags(article_id: str):
        cfg = current_config()
        db = get_db()
        article = db.get_article(article_id)
        if not article:
            flash("Article not found", "warning")
            return redirect(url_for("dashboard"))

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
                return redirect(url_for("edit_tags", article_id=article_id))

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

    @app.route("/run-pipeline", methods=["POST"])
    def run_pipeline():
        cfg = current_config()
        try:
            pipeline = IngestionPipeline(cfg["config_path"])
            results = pipeline.run()
            flash(f"Pipeline completed: {len(results)} articles processed", "success")
        except Exception as exc:
            flash(f"Pipeline failed: {exc}", "danger")
        return redirect(url_for("dashboard"))

    @app.route("/tag-feedback", methods=["POST"])
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
            return redirect(url_for("edit_tags", article_id=article_id))
        return redirect(url_for("dashboard"))

    @app.route("/articles/<article_id>/delete", methods=["POST"])
    def delete_article_route(article_id: str):
        db = get_db()
        if db.delete_article(article_id):
            flash("Article deleted", "success")
            event_logger.log("delete", f"Deleted article {article_id[:8]}...", level="warning")
        else:
            flash("Failed to delete article", "danger")
            event_logger.log("delete", f"Failed to delete article {article_id}", level="error")
        return redirect(url_for("dashboard"))

    @app.route("/api/events")
    def api_events():
        limit = int(request.args.get("limit", 50))
        return jsonify(event_logger.get_recent(limit))

    @app.route("/api/pipeline/fetch", methods=["POST"])
    def api_pipeline_fetch():
        cfg = current_config()
        try:
            event_logger.log("pipeline", "Starting pipeline fetch...", level="info")
            pipeline = IngestionPipeline(cfg["config_path"])
            articles = pipeline.fetch()
            event_logger.log("pipeline", f"Fetched {len(articles)} articles", level="success", details={"count": len(articles)})
            return jsonify({
                "status": "success",
                "count": len(articles),
                "articles": articles
            })
        except Exception as e:
            msg = f"Pipeline fetch error: {e}"
            logger.error(msg)
            event_logger.log("pipeline", msg, level="error")
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/pipeline/process", methods=["POST"])
    def api_pipeline_process():
        cfg = current_config()
        article_data = request.json
        if not article_data:
            return jsonify({"status": "error", "message": "No article data provided"}), 400
            
        try:
            title = article_data.get("title", "Unknown")
            # event_logger.log("pipeline", f"Processing: {title}", level="info") # Too verbose? maybe handled by UI
            
            pipeline = IngestionPipeline(cfg["config_path"])
            result = pipeline.process_article(article_data)
            
            if result.get("status") == "imported":
                event_logger.log("pipeline", f"Imported: {title}", level="success", details=result)
                if result.get("alert"):
                    event_logger.log("alert", f"Alert triggered: {title}", level="warning", details=result)
            elif result.get("status") == "skipped":
                # event_logger.log("pipeline", f"Skipped: {title}", level="warning", details=result)
                pass
                
            return jsonify(result)
        except Exception as e:
            msg = f"Pipeline process error: {e}"
            logger.error(msg)
            event_logger.log("pipeline", msg, level="error")
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/pipeline/warmup", methods=["POST"])
    def api_pipeline_warmup():
        cfg = current_config()
        try:
            event_logger.log("system", "Warming up AI models...", level="info")
            ollama = build_ollama(cfg)
            if ollama.warmup():
                event_logger.log("system", "AI models ready", level="success")
                return jsonify({"status": "success", "message": "Ollama model warmed up"})
            else:
                event_logger.log("system", "Warmup failed", level="error")
                return jsonify({"status": "error", "message": "Warmup failed"}), 500
        except Exception as e:
            event_logger.log("system", f"Warmup error: {e}", level="error")
            logger.error(f"Warmup error: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500

    @app.route("/api/pipeline/complete", methods=["POST"])
    def api_pipeline_complete():
        cfg = current_config()
        data = request.json
        count = data.get("count", 0) if data else 0
        
        try:
            pipeline = IngestionPipeline(cfg["config_path"])
            pipeline.update_status(count)
            event_logger.log("pipeline", f"Pipeline run complete. Processed {count} items.", level="success")
            return jsonify({"status": "success", "message": "Status updated"})
        except Exception as e:
            logger.error(f"Status update error: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500



def current_config() -> Dict[str, Any]:
    return current_app.config["NEWSFINDER_CONFIG"]


def get_db() -> NewsDatabase:
    if "news_db" not in g:
        cfg = current_config()
        chroma_dir = cfg["storage"]["chroma_dir"]
        g.news_db = NewsDatabase(persist_directory=chroma_dir)
    return g.news_db


def build_ollama(cfg: Dict[str, Any]) -> OllamaClient:
    llm_cfg = cfg["llm"]
    return OllamaClient(
        base_url=llm_cfg["base_url"],
        model=llm_cfg["model"],
        embedding_model=llm_cfg["embedding_model"],
    )


def load_status(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data or {"last_run": "—", "articles_processed": 0}
    except (FileNotFoundError, json.JSONDecodeError):
        return {"last_run": "—", "articles_processed": 0}


def load_alerts(path: str, limit: int = 5) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        return []

    alerts: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle.readlines()[-limit:]:
            try:
                alerts.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                continue
    alerts.reverse()
    return alerts


def load_context(path: str) -> Dict[str, Any]:
    prompt = ""
    structured: Dict[str, Any] | None = None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            prompt = handle.read()
    except FileNotFoundError:
        prompt = "Context not generated yet."

    json_path = path + ".json"
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as handle:
            structured = json.load(handle)

    return {
        "prompt": prompt,
        "structured": structured,
    }


def enrich_context(context: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    structured = context.get("structured") or {}
    
    # Handle new multi-company format
    if "companies" in structured and isinstance(structured["companies"], list):
        # Already in new format, just ensure defaults for each if needed
        # (Though profiler should have handled it, we can be safe)
        pass 
    else:
        # Legacy or empty: Try to migrate or init from config
        # If structured has data but no 'companies' key, wrap it?
        # Or just rebuild from config.
        
        # Let's rebuild structure based on Config to ensure alignment
        cfg_companies = cfg.get("companies", [])
        if not cfg_companies and cfg.get("company"):
             cfg_companies = [cfg["company"]]
             
        structured_companies = []
        
        # If we have legacy structured data, maybe we can use it for the first company
        legacy_data = structured if structured.get("company_name") else None
        
        for idx, comp_cfg in enumerate(cfg_companies):
            if idx == 0 and legacy_data:
                # Use existing data for primary
                structured_companies.append(legacy_data)
            else:
                # Create default/empty placeholder
                structured_companies.append(default_company_structure(cfg, comp_cfg.get("name", "Company"), comp_cfg.get("url", "")))
        
        structured = {"companies": structured_companies}

    context["structured"] = structured
    return context


def derive_company_name(url: str) -> str:
    if not url:
        return "Company"
    parsed = urlparse(url)
    host = parsed.netloc or parsed.path
    host = host.replace("www.", "")
    base = host.split(".")[0].replace("-", " ")
    if "wellness" in base and " " not in base:
        base = base.replace("wellness", " wellness")
    return base.title() or "Company"


def default_company_structure(cfg: Dict[str, Any], company_name: str, url: str = "") -> Dict[str, Any]:
    keywords = cfg.get("pipeline", {}).get("keywords", [])
    focus_keywords = [kw.lower() for kw in keywords] or [
        "preventive health",
        "health screening",
        "diagnostics",
    ]
    return {
        "company_name": company_name,
        "url": url,
        "offer_summary": "Affordable, nationwide health screening and wellness packages for individuals and employers.",
        "business_goals": [
            "Expand preventive health screening reach across the UK",
            "Promote early detection services to employers and consumers",
            "Differentiate through clinical quality and customer experience",
        ],
        "key_products": [
            "Comprehensive health screening packages",
            "On-site corporate wellness clinics",
            "Remote diagnostic tests",
        ],
        "market_position": "Preventive health screening provider focused on proactive wellness.",
        "focus_keywords": focus_keywords,
    }


def match_goals(text: str, goals: List[str]) -> List[str]:
    matches: List[str] = []
    for goal in goals:
        keywords = extract_keywords(goal)
        if any(keyword in text for keyword in keywords):
            matches.append(goal)
    return matches


def extract_keywords(text: str) -> List[str]:
    tokens = re.findall(r"[a-zA-Z]{4,}", text.lower())
    return [token for token in tokens if token not in STOPWORDS]


def derive_topic_tags(article: Dict[str, Any], keyword_matches: List[str]) -> List[str]:
    stored_tags = article.get("topic_tags")
    if isinstance(stored_tags, list) and stored_tags:
        return stored_tags
    if keyword_matches:
        return keyword_matches

    title = article.get("title", "")
    summary = article.get("summary_text", "")
    keywords = extract_keywords(f"{title} {summary}")
    return keywords[:4]


def generate_tag_rationale(
    ollama: OllamaClient,
    article: Dict[str, Any],
    topic_tags: List[str],
    entity_tags: List[str],
) -> str:
    prompt = f"""
    You are explaining why article tags were chosen. Provide a short explanation
    (2-3 sentences) tying tags to the article summary.

    Article Title: {article.get('title', '')}
    Article Summary: {article.get('summary_text', '')}
    Topic Tags: {', '.join(topic_tags)}
    Entity Tags: {', '.join(entity_tags)}
    """

    response = ollama.generate_json(
        prompt + "\nReturn JSON with field: rationale"
    )
    if not response:
        return ""
    return str(response.get("rationale", "")).strip()


def save_config(new_config: Dict[str, Any]) -> None:
    config_path = new_config.get("config_path") or current_config().get("config_path")
    if not config_path:
        raise ValueError("Config path is not set")

    # Remove runtime-only entries
    cleaned = copy.deepcopy(new_config)
    cleaned.pop("config_path", None)

    with open(config_path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(cleaned, handle, sort_keys=False, allow_unicode=True)

    current_app.config["NEWSFINDER_CONFIG"] = load_config(config_path)


def register_teardown(app: Flask) -> None:
    @app.teardown_appcontext
    def teardown_db(_exc):  # type: ignore[func-returns-value]
        g.pop("news_db", None)


if __name__ == "__main__":
    application = create_app()
    web_cfg = application.config["NEWSFINDER_CONFIG"]["web"]
    application.run(host=web_cfg.get("host", "0.0.0.0"), port=web_cfg.get("port", 5000))
