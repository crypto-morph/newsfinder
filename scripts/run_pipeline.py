#!/usr/bin/env python3
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pipeline import IngestionPipeline
from src.settings import load_config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

def main():
    logger.info("Starting pipeline run...")
    pipeline = IngestionPipeline()
    
    try:
        results = pipeline.run()
        logger.info("Pipeline completed successfully")
        if isinstance(results, list):
            logger.info(f"Total articles processed: {len(results)}")
        else:
            logger.info(f"Total articles processed: {results.get('total', 0)}")
            logger.info(f"New articles: {results.get('new', 0)}")
            logger.info(f"Alerts generated: {results.get('alerts', 0)}")
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
