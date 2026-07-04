from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class ScreenshotRecord:
    tab_name: str
    file_path: Path
    created_at: datetime
    duration_ms: int
    size_bytes: int
