import json
import threading
from pathlib import Path


class JsonlLogger:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()

    def write(self, payload):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False)
        with self.lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
