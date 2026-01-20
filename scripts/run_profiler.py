#!/usr/bin/env python3
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.context_profiler import CompanyContextProfiler
from src.settings import load_config
from src.ollama_monitor import check_ollama_status, ensure_model_available

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

def main():
    logger.info("Starting context profiler...")
    cfg = load_config()
    
    # Check Ollama status
    llm_config = cfg.get("llm", {})
    base_url = llm_config.get("base_url", "http://localhost:11434")
    model = llm_config.get("model", "llama3.2:3b")
    
    logger.info("Checking Ollama status...")
    status = check_ollama_status(base_url)
    
    if status["status"] == "stopped":
        logger.error("❌ Ollama is not running! Start it with: ollama serve")
        sys.exit(1)
    elif status["status"] == "error":
        logger.error(f"❌ Ollama error: {status.get('message')}")
        sys.exit(1)
    
    logger.info(f"✓ Ollama is running ({len(status.get('loaded_models', []))} models loaded)")
    
    if not ensure_model_available(model, base_url):
        logger.error(f"❌ Required model '{model}' not available")
        sys.exit(1)
    
    profiler = CompanyContextProfiler()
    
    try:
        contexts = profiler.refresh_all_contexts()
        logger.info(f"✓ Successfully refreshed context for {len(contexts)} companies")
        for ctx in contexts:
            logger.info(f"  - {ctx.company_name}: {len(ctx.business_goals)} goals, {len(ctx.key_products)} products")
    except Exception as e:
        logger.error(f"Profiler failed: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
