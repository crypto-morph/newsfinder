from flask import Blueprint, jsonify, request
from src.web.utils import current_config, event_logger, build_ollama
from src.pipeline import IngestionPipeline
import logging

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api")

@api_bp.route("/events")
def api_events():
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
    return jsonify(event_logger.get_recent(limit, offset))

@api_bp.route("/pipeline/fetch", methods=["POST"])
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

@api_bp.route("/pipeline/process", methods=["POST"])
def api_pipeline_process():
    cfg = current_config()
    article_data = request.json
    if not article_data:
        return jsonify({"status": "error", "message": "No article data provided"}), 400
        
    try:
        title = article_data.get("title", "Unknown")
        
        pipeline = IngestionPipeline(cfg["config_path"])
        result = pipeline.process_article(article_data)
        
        if result.get("status") == "imported":
            event_logger.log("pipeline", f"Imported: {title}", level="success", details=result)
            if result.get("alert"):
                event_logger.log("alert", f"Alert triggered: {title}", level="warning", details=result)
        elif result.get("status") == "skipped":
            pass
            
        return jsonify(result)
    except Exception as e:
        msg = f"Pipeline process error: {e}"
        logger.error(msg)
        event_logger.log("pipeline", msg, level="error")
        return jsonify({"status": "error", "message": str(e)}), 500

@api_bp.route("/pipeline/warmup", methods=["POST"])
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

@api_bp.route("/pipeline/complete", methods=["POST"])
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
