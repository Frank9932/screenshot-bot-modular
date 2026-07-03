import time
import uuid
from pathlib import Path

from screenshot_bot.config import get_section, load_json_config, resolve_path

from .devtools_client import capture_page_png, find_page
from .profile_manager import BrowserProfileManager
from .target_config import BrowserTargetConfig
from .watermark import WatermarkRenderer


class BrowserScreenshotService:
    def __init__(self, config_path):
        self.config_path = config_path
        self.config = load_json_config(config_path)
        self.targets = BrowserTargetConfig(config_path, self.config)
        self.profile_manager = BrowserProfileManager(config_path, self.targets.section)
        self.watermark = WatermarkRenderer(get_section(self.config, "watermark"))

    def parse_team_id(self, text):
        return self.targets.parse_number(text)

    def capture(self, team_id, output_dir=None, image_name=None, timeout_seconds=15):
        target = self.targets.get_target(team_id)
        port = int(target["debug_port"])
        image_name = image_name or f"browser-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}.png"
        output_dir = Path(output_dir) if output_dir else resolve_path(self.config_path, "screenshots", "screenshots")
        output_dir.mkdir(parents=True, exist_ok=True)
        raw_dir = resolve_path(self.config_path, self.targets.section.get("raw_dir"), "screenshots/browser-raw")
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / image_name
        final_path = output_dir / image_name

        startup_info = self.profile_manager.ensure_running(team_id, target)
        started = time.perf_counter()
        page = find_page(port, target)
        raw_path.write_bytes(capture_page_png(page["webSocketDebuggerUrl"], timeout_seconds=timeout_seconds))
        capture_ms = (time.perf_counter() - started) * 1000.0

        watermark_started = time.perf_counter()
        dynamic = {
            "team_id": team_id,
            "target_name": target.get("name", team_id),
            "page_title": page.get("title", ""),
            "page_url": page.get("url", ""),
            "capture_ms": f"{capture_ms:.0f}",
        }
        watermark_info = self.watermark.apply(raw_path, final_path, dynamic)
        watermark_ms = (time.perf_counter() - watermark_started) * 1000.0
        return {
            "source": "chrome_devtools",
            "team_id": str(team_id),
            "target_name": target.get("name", str(team_id)),
            "debug_port": port,
            "browser_startup": startup_info,
            "page_title": page.get("title", ""),
            "page_url": page.get("url", ""),
            "raw_path": str(raw_path),
            "published_path": str(final_path),
            "capture_ms": capture_ms,
            "watermark_ms": watermark_ms,
            **watermark_info,
        }
