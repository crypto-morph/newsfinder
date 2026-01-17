import json
import os
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

class EventLogger:
    def __init__(self, log_path: str = "logs/events.jsonl"):
        self.log_path = log_path
        os.makedirs(os.path.dirname(log_path), exist_ok=True)

    def log(self, event_type: str, message: str, level: str = "info", details: Optional[Dict] = None):
        """
        Log an event to the persistent store.
        """
        event = {
            "timestamp": time.time(),
            "iso_time": datetime.utcnow().isoformat(),
            "type": event_type,
            "level": level,
            "message": message,
            "details": details or {}
        }
        
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"Failed to write to event log: {e}")

    def get_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get the most recent events.
        """
        events = []
        if not os.path.exists(self.log_path):
            return []
            
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                # Read all lines (efficient enough for reasonable log sizes, 
                # for massive logs we'd seek from end)
                lines = f.readlines()
                for line in reversed(lines):
                    if len(events) >= limit:
                        break
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            print(f"Failed to read event log: {e}")
            
        return events

# Global instance will be created in app context
