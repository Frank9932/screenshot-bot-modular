import threading
import time


class MessageDedupe:
    def __init__(self, ttl_seconds=600):
        self.ttl_seconds = float(ttl_seconds)
        self._seen = {}
        self._lock = threading.Lock()

    def mark_first_seen(self, key):
        now = time.time()
        with self._lock:
            expired = [item for item, stamp in self._seen.items() if now - stamp > self.ttl_seconds]
            for item in expired:
                self._seen.pop(item, None)
            if key in self._seen:
                return False
            self._seen[key] = now
            return True
