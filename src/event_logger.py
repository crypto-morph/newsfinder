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

    def get_recent(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get recent events with pagination.
        offset: Number of most recent events to skip.
        limit: Number of events to return.
        """
        events = []
        if not os.path.exists(self.log_path):
            return []
            
        try:
            with open(self.log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                # We want newest first, so reverse the list
                # Then slice based on offset and limit
                # lines_reversed = list(reversed(lines)) # Inefficient for huge files but ok for now
                
                # Better: iterate backwards using index
                total_lines = len(lines)
                start_idx = total_lines - 1 - offset
                end_idx = start_idx - limit
                
                if start_idx < 0:
                    return []
                    
                # Ensure we don't go below index -1
                stop_idx = max(end_idx, -1)
                
                for i in range(start_idx, stop_idx, -1):
                    try:
                        events.append(json.loads(lines[i]))
                    except json.JSONDecodeError:
                        continue
                        
        except Exception as e:
            print(f"Failed to read event log: {e}")
            
        return events

# Global instance will be created in app context
