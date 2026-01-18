import json
import logging
import random
import os
from datetime import datetime, timezone
from typing import Dict, Optional, List
from src.analysis.openrouter_client import OpenRouterClient
from src.event_logger import EventLogger

logger = logging.getLogger(__name__)

class VerificationService:
    def __init__(self, config: Dict):
        self.config = config.get("verification", {})
        self.enabled = self.config.get("enabled", False)
        # Use a default model if not configured
        self.client = OpenRouterClient(model=self.config.get("model", "google/gemini-2.0-flash-001"))
        self.log_file = self.config.get("log_file", "logs/verification.jsonl")
        self.event_logger = EventLogger()
        
        # Sampling rates
        self.rate_interesting = self.config.get("sample_rate_interesting", 1.0)
        self.rate_random = self.config.get("sample_rate_random", 0.1)

    def should_verify(self, local_result: Dict) -> bool:
        """Determine if an article should be verified based on sampling rules."""
        if not self.enabled or not self.client.api_key:
            return False
            
        # Check if local model thought it was relevant
        local_score = local_result.get("relevance_score", 0)
        is_interesting = local_score >= 7
        
        if is_interesting:
            return random.random() < self.rate_interesting
        else:
            return random.random() < self.rate_random

    def verify(self, article: Dict, local_result: Dict, context: str) -> Optional[Dict]:
        """
        Run verification if needed.
        Returns the verification record if verification ran, otherwise None.
        """
        if not self.should_verify(local_result):
            return None
            
        logger.info(f"Verifying article with OpenRouter: {article.get('title')}")
        
        remote_result = self.client.analyze_article(article.get("content", ""), context)
        
        if not remote_result:
            return None
            
        # Compare results
        local_score = local_result.get("relevance_score", 0)
        remote_score = remote_result.get("relevance_score", 0)
        
        # Calculate discrepancy
        discrepancy = abs(local_score - remote_score)
        # Flag if difference is significant (e.g. High vs Low)
        # >= 4 means e.g. 7 (High) vs 3 (Low) or 8 vs 4
        flagged = discrepancy >= 4
        
        verification_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "article_title": article.get("title"),
            "article_url": article.get("link"),
            "local_model": "local", # Could pull actual name from config if passed
            "remote_model": self.client.model,
            "local_score": local_score,
            "remote_score": remote_score,
            "local_reasoning": local_result.get("relevance_reasoning"),
            "remote_reasoning": remote_result.get("relevance_reasoning"),
            "discrepancy": discrepancy,
            "flagged": flagged
        }
        
        self._log_verification(verification_record)
        
        if flagged:
            msg = f"Verification Mismatch! Local: {local_score}, Remote: {remote_score} for '{article.get('title')}'"
            logger.warning(msg)
            self.event_logger.log("verification", msg, level="warning", details=verification_record)
            
        return verification_record

    def _log_verification(self, record: Dict):
        """Append verification record to JSONL log."""
        try:
            os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Failed to log verification: {e}")

    def get_recent_verifications(self, limit: int = 50) -> List[Dict]:
        """Retrieve recent verification logs."""
        results = []
        if not os.path.exists(self.log_file):
            return []
            
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                # Read all lines
                lines = f.readlines()
                # Parse valid JSON lines
                for line in lines:
                    try:
                        if line.strip():
                            results.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                        
            # Sort by timestamp descending (newest first)
            return sorted(results, key=lambda x: x.get("timestamp", ""), reverse=True)[:limit]
        except Exception as e:
            logger.error(f"Error reading verification log: {e}")
            return []
