
import os
import json
import time
from typing import Any, Optional, Tuple

class SimpleCache:
    def __init__(self, cache_dir: str = ".mcp_cache"):
        self.cache_dir = cache_dir
        if not os.path.exists(cache_dir):
            try:
                os.makedirs(cache_dir, exist_ok=True)
            except Exception:
                # Fallback to tmp if current dir not writable
                import tempfile
                self.cache_dir = os.path.join(tempfile.gettempdir(), "mcp_cache")
                os.makedirs(self.cache_dir, exist_ok=True)

    def _get_path(self, key: str) -> str:
        # Simple sanitization
        safe_key = "".join(c if c.isalnum() else "_" for c in key)
        return os.path.join(self.cache_dir, f"{safe_key}.json")

    def get(self, key: str, ttl_seconds: float) -> Optional[Any]:
        path = self._get_path(key)
        if not os.path.exists(path):
            return None
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            ts = data.get("ts", 0)
            if time.time() - ts > ttl_seconds:
                return None
            
            return data.get("payload")
        except Exception:
            return None

    def set(self, key: str, value: Any):
        path = self._get_path(key)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({
                    "ts": time.time(),
                    "payload": value
                }, f)
        except Exception as e:
            import sys
            print(f"Cache write failed: {e}", file=sys.stderr)

# Global instance
cache = SimpleCache()
