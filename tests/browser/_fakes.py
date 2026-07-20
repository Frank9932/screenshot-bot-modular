"""Shared fakes for browser/ contract tests -- stand in for the real Chrome/CDP boundary
(CdpMultiTabService + BrowserProfileManager) so BrowserScreenshotService.capture() can be
driven through every success/failure path with no real Chrome process, no real network, and
no real login credentials. Swapped in by replacing `BrowserScreenshotService.profile_manager`
after construction (construction itself never touches Chrome -- only capture()/warm_up() do)."""

import io
import json
from pathlib import Path

from PIL import Image

from screenshot_bot.browser import BrowserScreenshotService


def _tiny_png_bytes():
    # WatermarkRenderer.apply() opens raw_path as a real image (Image.open), so the fake
    # screenshot bytes must be a real, decodable PNG -- not arbitrary placeholder bytes.
    buffer = io.BytesIO()
    Image.new("RGB", (2, 2), (10, 20, 30)).save(buffer, "PNG")
    return buffer.getvalue()


class FakeCdpService:
    """Stands in for CdpMultiTabService's screenshot/navigate_equipment/list_tabs surface."""

    def __init__(self, screenshot_bytes=None, screenshot_exc=None, navigate_exc=None, tabs=None):
        screenshot_bytes = screenshot_bytes if screenshot_bytes is not None else _tiny_png_bytes()
        self.screenshot_bytes = screenshot_bytes
        self.screenshot_exc = screenshot_exc
        self.navigate_exc = navigate_exc
        self.tabs = tabs if tabs is not None else []
        self.screenshot_calls = []
        self.navigate_calls = []

    def navigate_equipment(self, name, path, pane_height="12%", settle_seconds=3.0, timeout_seconds=35):
        self.navigate_calls.append({"name": name, "path": path, "timeout_seconds": timeout_seconds})
        if self.navigate_exc:
            raise self.navigate_exc
        return {"name": name, "path": path}

    def screenshot(self, name, output_path=None, timeout_seconds=15):
        self.screenshot_calls.append({"name": name, "output_path": output_path, "timeout_seconds": timeout_seconds})
        if self.screenshot_exc:
            raise self.screenshot_exc
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(self.screenshot_bytes)
        return {
            "name": name,
            "elapsed_ms": 12.5,
            "path": str(output_path) if output_path else None,
            "bytes": self.screenshot_bytes,
        }

    def list_tabs(self):
        return self.tabs


class FakeProfileManager:
    """Stands in for BrowserProfileManager -- the piece that owns Chrome launch/tab
    provisioning/login. `ensure_tab_exc`, if set, is what capture() sees for every kind of
    provisioning failure (Chrome unreachable, executable missing, login rejected, tab not
    debuggable at creation time, etc.) since they all surface identically to capture(): an
    exception raised out of ensure_tab()."""

    def __init__(self, service, tab_name="test-target", ensure_tab_exc=None, port=9222):
        self.service = service
        self.port = port
        self._tab_name = tab_name
        self._ensure_tab_exc = ensure_tab_exc
        self.ensure_tab_calls = []

    def ensure_tab(self, team_id, target, tab_index=0):
        self.ensure_tab_calls.append({"team_id": team_id, "tab_index": tab_index})
        if self._ensure_tab_exc:
            raise self._ensure_tab_exc
        return self._tab_name, {"started": False, "port": self.port}


def build_service(tmp_path, cdp_service=None, ensure_tab_exc=None, targets=None):
    """A real BrowserScreenshotService (real config load, real target parsing, real
    ScreenshotStore, real -- but disabled -- watermark renderer) with its profile_manager
    swapped for a fake, so capture() runs its actual production logic end-to-end except for
    the Chrome/CDP boundary itself."""
    config = {
        "browser_targets": {
            "enabled": True,
            "debug_port": 9222,
            "store_dir": "storage/screenshots",
            "raw_dir": "screenshots/browser-raw",
            "targets": targets
            or {
                "1": {
                    "name": "test-target",
                    "start_url": "https://example.test/login.html",
                    "app_url": "https://example.test/",
                    "tab": 0,
                }
            },
        },
        # Disabled so watermark.apply() takes its no-op copy path -- keeps these tests from
        # depending on any system font being installed.
        "watermark": {"enabled": False},
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    service = BrowserScreenshotService(str(config_path))
    cdp = cdp_service if cdp_service is not None else FakeCdpService()
    service.profile_manager = FakeProfileManager(cdp, ensure_tab_exc=ensure_tab_exc)
    return service, cdp
