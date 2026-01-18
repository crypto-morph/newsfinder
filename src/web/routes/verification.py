from flask import Blueprint, render_template, request, jsonify, flash
from src.web.utils import current_config, event_logger
from src.analysis.verification_service import VerificationService
from src.analysis.optimizer import PromptOptimizer
import logging

logger = logging.getLogger(__name__)

verification_bp = Blueprint("verification", __name__)

@verification_bp.route("/verification")
def verification_view():
    cfg = current_config()
    service = VerificationService(cfg)
    verifications = service.get_recent_verifications(limit=50)
    
    ver_cfg = cfg.get("verification", {})
    
    # Load current prompt for display
    optimizer = PromptOptimizer(cfg["config_path"])
    current_prompt = optimizer.load_current_prompt()

    return render_template(
        "verification.html",
        verifications=verifications,
        active_page="verification_view",
        local_model=cfg["llm"]["model"],
        provider_model=ver_cfg.get("model", "Unknown"),
        sample_rate_high=ver_cfg.get("sample_rate_interesting", 1.0),
        sample_rate_random=ver_cfg.get("sample_rate_random", 0.1),
        current_prompt=current_prompt
    )

@verification_bp.route("/verification/optimize", methods=["POST"])
def optimize_prompt():
    cfg = current_config()
    
    try:
        optimizer = PromptOptimizer(cfg["config_path"])
        current_prompt = optimizer.load_current_prompt()
        failures = optimizer.get_failure_cases(limit=5)
        
        if not failures:
            return jsonify({"status": "error", "message": "No failure cases found to optimize against."})
            
        new_prompt = optimizer.generate_optimized_prompt(current_prompt, failures)
        
        if not new_prompt:
            return jsonify({"status": "error", "message": "Failed to generate optimized prompt."})
            
        return jsonify({
            "status": "success", 
            "new_prompt": new_prompt,
            "failure_count": len(failures)
        })
    except Exception as e:
        logger.error(f"Optimization error: {e}")
        return jsonify({"status": "error", "message": str(e)})

@verification_bp.route("/verification/test", methods=["POST"])
def test_optimized_prompt():
    cfg = current_config()
    
    new_prompt = request.json.get("prompt")
    if not new_prompt:
            return jsonify({"status": "error", "message": "No prompt provided"})

    try:
        optimizer = PromptOptimizer(cfg["config_path"])
        failures = optimizer.get_failure_cases(limit=5)
        results = optimizer.test_prompt(new_prompt, failures)
        
        return jsonify({"status": "success", "results": results})
    except Exception as e:
            logger.error(f"Test error: {e}")
            return jsonify({"status": "error", "message": str(e)})

@verification_bp.route("/verification/apply", methods=["POST"])
def apply_prompt():
    cfg = current_config()
    
    new_prompt = request.json.get("prompt")
    if not new_prompt:
            return jsonify({"status": "error", "message": "No prompt provided"})

    try:
        optimizer = PromptOptimizer(cfg["config_path"])
        if optimizer.save_prompt(new_prompt):
            flash("New prompt applied successfully", "success")
            return jsonify({"status": "success"})
        else:
            return jsonify({"status": "error", "message": "Failed to save prompt"})
    except Exception as e:
            logger.error(f"Apply error: {e}")
            return jsonify({"status": "error", "message": str(e)})
