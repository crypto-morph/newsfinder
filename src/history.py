
import json
import os
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class HistoryManager:
    def __init__(self, history_file: str = "data/article_history.jsonl"):
        self.history_file = history_file
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)

    def log_change(self, article_id: str, old_data: Dict, new_data: Dict, change_type: str = "reappraisal") -> Dict:
        """
        Log a change in article state.
        Only logs fields that are relevant for history (scores, reasoning, status).
        Returns the diff dictionary.
        """
        timestamp = datetime.utcnow().isoformat()
        
        # Calculate diffs
        changes = {}
        fields_to_track = [
            "relevance_score", "relevance_reasoning", 
            "impact_score", "status", "summary_text"
        ]
        
        has_changes = False
        for field in fields_to_track:
            old_val = old_data.get(field)
            new_val = new_data.get(field)
            
            # Normalization for comparison
            if old_val != new_val:
                changes[field] = {
                    "from": old_val,
                    "to": new_val
                }
                has_changes = True
        
        if not has_changes and change_type == "reappraisal":
            # Even if no score change, we might want to log that it was checked
            pass

        entry = {
            "timestamp": timestamp,
            "article_id": article_id,
            "type": change_type,
            "changes": changes,
            "snapshot": {k: new_data.get(k) for k in fields_to_track if k in new_data}
        }
        
        try:
            with open(self.history_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to write history log: {e}")
            
        return changes

    def get_history(self, article_id: str) -> List[Dict]:
        """
        Retrieve history for a specific article.
        """
        if not os.path.exists(self.history_file):
            return []
            
        history = []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        if entry.get("article_id") == article_id:
                            history.append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"Failed to read history log: {e}")
            
        return sorted(history, key=lambda x: x["timestamp"], reverse=True)

    def get_recent_history(self, limit: int = 50) -> List[Dict]:
        """
        Get all recent history events.
        """
        if not os.path.exists(self.history_file):
            return []
            
        # Read file backwards ideally, but for now just read all
        events = []
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        events.append(json.loads(line))
                    except:
                        pass
        except Exception:
            return []
            
        return sorted(events, key=lambda x: x["timestamp"], reverse=True)[:limit]

    def get_history_map(self) -> Dict[str, List[Dict]]:
        """
        Load all history grouped by article_id.
        Returns: {article_id: [history_entries]}
        """
        if not os.path.exists(self.history_file):
            return {}
            
        history_map = {}
        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        aid = entry.get("article_id")
                        if aid:
                            if aid not in history_map:
                                history_map[aid] = []
                            history_map[aid].append(entry)
                    except:
                        pass
        except Exception as e:
            logger.error(f"Failed to read history log: {e}")
            
        # Sort each list
        for aid in history_map:
            history_map[aid].sort(key=lambda x: x["timestamp"], reverse=True)
            
        return history_map
