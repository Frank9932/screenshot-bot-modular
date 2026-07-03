import shutil
import subprocess
import time
from pathlib import Path

from screenshot_bot.config import resolve_path


class DesktopScreenshotService:
    def __init__(self, config_path, screenshot_tool="ScreenshotTool.exe", screenshot_dir="screenshots"):
        self.config_path = config_path
        self.screenshot_tool = resolve_path(config_path, screenshot_tool, "ScreenshotTool.exe")
        self.screenshot_dir = resolve_path(config_path, screenshot_dir, "screenshots")
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)

    def capture(self, output_dir=None, image_name=None, timeout_seconds=15):
        if not self.screenshot_tool.is_file():
            raise FileNotFoundError(f"screenshot tool not found: {self.screenshot_tool}")
        command = [
            str(self.screenshot_tool),
            "--config",
            str(Path(self.config_path).resolve()),
            "--output-dir",
            str(self.screenshot_dir.resolve()),
        ]
        started = time.perf_counter()
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout_seconds)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if result.returncode != 0:
            raise RuntimeError(f"ScreenshotTool failed exit={result.returncode}: {result.stderr or result.stdout}")
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if not lines:
            raise RuntimeError("ScreenshotTool did not print an output path")
        source = Path(lines[-1])
        if not source.is_file():
            raise FileNotFoundError(f"ScreenshotTool output not found: {source}")
        if output_dir and image_name:
            target = Path(output_dir) / image_name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            return {"source_path": str(source), "published_path": str(target), "capture_ms": elapsed_ms}
        return {"source_path": str(source), "published_path": str(source), "capture_ms": elapsed_ms}
