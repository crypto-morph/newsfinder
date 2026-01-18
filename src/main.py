import logging
import sys
import os

# Ensure src is in path if running from root
sys.path.append(os.getcwd())

from apscheduler.schedulers.background import BackgroundScheduler
from src.web.app import create_app
from src.pipeline import IngestionPipeline
from src.settings import load_config

logger = logging.getLogger("newsfinder")

def run_pipeline_job(config_path):
    logger.info("Scheduler: Starting pipeline job...")
    try:
        pipeline = IngestionPipeline(config_path)
        pipeline.run()
        logger.info("Scheduler: Pipeline job finished.")
    except Exception as e:
        logger.error(f"Scheduler: Pipeline job failed: {e}", exc_info=True)

def main():
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    config_path = "config.yaml"
    config = load_config(config_path)
    
    # Setup Scheduler
    scheduler_conf = config.get("scheduler", {})
    if scheduler_conf.get("enabled", True):
        scheduler = BackgroundScheduler()
        interval = scheduler_conf.get("interval_minutes", 60)
        
        # Add job
        scheduler.add_job(
            run_pipeline_job, 
            'interval', 
            minutes=interval, 
            args=[config_path],
            id='pipeline_job'
        )
        
        # Run immediately on startup if requested (optional, maybe not for dev)
        # run_pipeline_job(config_path) 
        
        scheduler.start()
        logger.info(f"Scheduler started with interval {interval} minutes.")
    
    # Start Web App
    app = create_app(config_path)
    web_conf = config.get("web", {})
    host = web_conf.get("host", "0.0.0.0")
    port = web_conf.get("port", 5000)
    
    logger.info(f"Starting web server on {host}:{port}")
    # Disable reloader to prevent scheduler running twice in dev
    app.run(host=host, port=port, debug=True, use_reloader=False)

if __name__ == "__main__":
    main()
