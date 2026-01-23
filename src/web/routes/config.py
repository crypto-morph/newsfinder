from flask import Blueprint, render_template, request, flash, redirect, url_for
from src.web.utils import (
    current_config, save_config, load_context, enrich_context, event_logger
)
from src.context_profiler import CompanyContextProfiler
from src.aggregator.rss_scraper import RSSNewsAggregator
import copy
import json
import logging

logger = logging.getLogger(__name__)

config_bp = Blueprint("config", __name__)

@config_bp.route("/config", methods=["GET", "POST"])
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

        elif action == "add_prompt_rule":
            new_rule = request.form.get("rule", "").strip()
            if new_rule:
                rules = cfg.get("llm", {}).get("prompt_rules", [])
                rules.append(new_rule)
                updated = copy.deepcopy(cfg)
                updated.setdefault("llm", {})["prompt_rules"] = rules
                save_config(updated)
                flash("Prompt rule added", "success")
                event_logger.log("config", f"Added prompt rule", level="info")

        elif action == "remove_prompt_rule":
            index = int(request.form.get("index", -1))
            rules = cfg.get("llm", {}).get("prompt_rules", [])
            if 0 <= index < len(rules):
                removed = rules.pop(index)
                updated = copy.deepcopy(cfg)
                updated.setdefault("llm", {})["prompt_rules"] = rules
                save_config(updated)
                flash("Prompt rule removed", "success")
                event_logger.log("config", f"Removed prompt rule", level="info")

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

        return redirect(url_for("config.config_view"))

    return render_template(
        "config.html",
        config=config_data,
        context=context,
        config_json=config_json,
        keywords_text=keywords_text,
        active_page="config",
    )

@config_bp.route("/sources", methods=["GET", "POST"])
def sources():
    cfg = current_config()
    feeds = list(cfg.get("feeds", []))
    preview = []
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
