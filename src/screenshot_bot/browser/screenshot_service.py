import time
import uuid
from pathlib import Path

from screenshot_bot.config import get_section, load_json_config, resolve_path
from screenshot_bot.screenshot_store import ScreenshotStore

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
        self.store = ScreenshotStore(
            base_dir=resolve_path(config_path, self.targets.section.get("store_dir"), "storage/screenshots")
        )

    def parse_team_id(self, text):
        return self.targets.parse_number(text)

    def warm_up(self):
        """Open (and log into, where configured) every tab of every target up front, instead of
        waiting for the first WeChat message to trigger it. One target's failure (e.g. a missing
        login env var) is recorded and skipped rather than aborting the rest — ensure_tab() will
        retry that target's login on the next capture() or warm_up() call since a failed login
        is never marked as applied (see BrowserProfileManager.ensure_tab).

        Several team_ids can share one underlying target (e.g. team 1-5 each pinned to one tab
        of the same login-gated site, all with `name: webstation-test`) — such a target is only
        actually opened/logged into once, the first time its name is seen, not once per team_id.
        Without this, a slow first login (still mid-navigation) would get hit with a second,
        third, fourth concurrent login() attempt on the very same tab as the next team_ids in
        this same loop ran their own copy of the full tab range, causing exactly the kind of
        connection-aborted/tab-not-debuggable cascade a single clean pass avoids."""
        results = {}
        if not self.targets.enabled:
            return results
        processed_by_name = {}
        for team_id, target in self.targets.targets.items():
            target_name = str(target.get("name", team_id))
            if target_name in processed_by_name:
                results[str(team_id)] = processed_by_name[target_name]
                continue
            tabs, errors = [], []
            for tab_index in range(self.profile_manager.tab_count(target)):
                try:
                    tab_name, _ = self.profile_manager.ensure_tab(team_id, target, tab_index=tab_index)
                    tabs.append(tab_name)
                except Exception as exc:
                    errors.append(f"tab {tab_index}: {exc}")
            entry = {"target_name": target_name, "tabs": tabs, "errors": errors}
            processed_by_name[target_name] = entry
            results[str(team_id)] = entry
        return results

    def capture(self, team_id, tab=None, user_id=None, output_dir=None, image_name=None, timeout_seconds=15):
        target = self.targets.get_target(team_id)
        # A team_id's own config declares which tab it means (several team_ids can share one
        # underlying multi-tab target, e.g. team 1-5 each pinned to one of the same site's 5
        # tabs). Callers doing their own tab bookkeeping (demo/audit scripts) can still pass an
        # explicit `tab` to override it.
        tab = int(target.get("tab", 0)) if tab is None else tab
        image_name = image_name or f"browser-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}.png"
        output_dir = Path(output_dir) if output_dir else resolve_path(self.config_path, "screenshots", "screenshots")
        output_dir.mkdir(parents=True, exist_ok=True)
        raw_dir = resolve_path(self.config_path, self.targets.section.get("raw_dir"), "screenshots/browser-raw")
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_path = raw_dir / image_name
        final_path = output_dir / image_name

        tab_name, startup_info = self.profile_manager.ensure_tab(team_id, target, tab_index=tab)
        capture_result = self.profile_manager.service.screenshot(
            tab_name, output_path=raw_path, timeout_seconds=timeout_seconds
        )
        capture_ms = capture_result["elapsed_ms"]
        page = next((t for t in self.profile_manager.service.list_tabs() if t["name"] == tab_name), {})

        target_name = str(target.get("name", team_id))
        # Organized by requester (WeChat user id) first, tab second, so a user's capture history
        # is easy to audit; falls back to target_name for non-WeChat callers with no user_id.
        store_key = f"{user_id}/tab_{tab}" if user_id else f"{target_name}/tab_{tab}"
        store_record = self.store.save_screenshot(store_key, capture_result["bytes"], duration_ms=round(capture_ms))

        watermark_started = time.perf_counter()
        dynamic = {
            "team_id": team_id,
            "target_name": target_name,
            "user_id": user_id or "",
            "page_title": page.get("title", ""),
            "page_url": page.get("url", ""),
            "capture_ms": f"{capture_ms:.0f}",
        }
        watermark_info = self.watermark.apply(raw_path, final_path, dynamic)
        watermark_ms = (time.perf_counter() - watermark_started) * 1000.0
        return {
            "source": "chrome_devtools",
            "team_id": str(team_id),
            "target_name": target_name,
            "tab": tab,
            "user_id": user_id or "",
            "debug_port": self.profile_manager.port,
            "browser_startup": startup_info,
            "page_title": page.get("title", ""),
            "page_url": page.get("url", ""),
            "raw_path": str(raw_path),
            "published_path": str(final_path),
            "store_path": str(store_record.file_path),
            "capture_ms": capture_ms,
            "watermark_ms": watermark_ms,
            **watermark_info,
        }
