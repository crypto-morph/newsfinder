"""Ollama status monitoring utility."""
import logging
import requests
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def check_ollama_status(base_url: str = "http://localhost:11434") -> Dict[str, any]:
    """Check Ollama server status and loaded models."""
    try:
        # Check if server is running
        response = requests.get(f"{base_url}/api/tags", timeout=5)
        if response.status_code != 200:
            return {"status": "error", "message": "Ollama server returned error"}
        
        models = response.json().get("models", [])
        
        # Check running models
        ps_response = requests.get(f"{base_url}/api/ps", timeout=5)
        running_models = []
        if ps_response.status_code == 200:
            running_models = ps_response.json().get("models", [])
        
        return {
            "status": "running",
            "available_models": [m["name"] for m in models],
            "loaded_models": [m["name"] for m in running_models],
            "model_count": len(models)
        }
    except requests.exceptions.ConnectionError:
        return {"status": "stopped", "message": "Cannot connect to Ollama server"}
    except requests.exceptions.Timeout:
        return {"status": "timeout", "message": "Ollama server not responding"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def ensure_model_available(model_name: str, base_url: str = "http://localhost:11434") -> bool:
    """Check if a specific model is available."""
    status = check_ollama_status(base_url)
    if status["status"] != "running":
        logger.error(f"Ollama is {status['status']}: {status.get('message', '')}")
        return False
    
    if model_name not in status["available_models"]:
        logger.error(f"Model '{model_name}' not found. Available: {status['available_models']}")
        return False
    
    if model_name in status["loaded_models"]:
        logger.info(f"Model '{model_name}' is already loaded and ready")
    else:
        logger.info(f"Model '{model_name}' is available (will load on first use)")
    
    return True
