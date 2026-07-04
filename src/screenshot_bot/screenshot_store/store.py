from datetime import datetime
from pathlib import Path

from .models import ScreenshotRecord

DEFAULT_BASE_DIR = "storage/screenshots"


def _build_filename(captured_at: datetime, duration_ms: int) -> str:
    timestamp = f"{captured_at:%Y%m%d_%H%M%S}_{captured_at.microsecond // 1000:03d}"
    return f"{timestamp}_{duration_ms}ms.png"


class ScreenshotStore:
    def __init__(self, base_dir=DEFAULT_BASE_DIR):
        self.base_dir = Path(base_dir)

    def save_screenshot(self, tab_name: str, image_bytes: bytes, duration_ms: int) -> ScreenshotRecord:
        captured_at = datetime.now()
        tab_dir = self.base_dir / tab_name
        tab_dir.mkdir(parents=True, exist_ok=True)

        file_path = tab_dir / _build_filename(captured_at, duration_ms)
        file_path.write_bytes(image_bytes)

        return ScreenshotRecord(
            tab_name=tab_name,
            file_path=file_path,
            created_at=captured_at,
            duration_ms=duration_ms,
            size_bytes=len(image_bytes),
        )
