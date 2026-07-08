import time
import uuid
from pathlib import Path

from screenshot_bot.config import get_section, load_json_config, resolve_path
from screenshot_bot.screenshot_store import ScreenshotStore

from .profile_manager import BrowserProfileManager
from .target_config import BrowserTargetConfig
from .watermark import WatermarkRenderer
from .watermark_settings import TeamWatermarkSettingsStore, resolve_watermark_config


class BrowserScreenshotService:
    def __init__(self, config_path):
        self.config_path = config_path
        self.config = load_json_config(config_path)
        self.targets = BrowserTargetConfig(config_path, self.config)
        self.profile_manager = BrowserProfileManager(config_path, self.targets.section)
        self.watermark_config = get_section(self.config, "watermark")
        self.watermark = WatermarkRenderer(self.watermark_config)
        self.watermark_settings = TeamWatermarkSettingsStore(
            resolve_path(config_path, self.targets.section.get("watermark_settings_path"), "runtime/watermark-team-settings.json")
        )
        self.store = ScreenshotStore(
            base_dir=resolve_path(config_path, self.targets.section.get("store_dir"), "storage/screenshots")
        )

    def parse_team_id(self, text):
        return self.targets.parse_number(text)

    def warm_up(self, team_ids=None):
        """Open (and log into, where configured) each requested team's own tab up front, instead
        of waiting for the first WeChat message to trigger it. One team's failure (e.g. a missing
        login env var) is recorded and skipped rather than aborting the rest — ensure_tab() will
        retry that team's login on the next capture() or warm_up() call since a failed login
        is never marked as applied (see BrowserProfileManager.ensure_tab).

        Several team_ids can share one underlying target (e.g. team 1-5 each pinned to one tab
        of the same login-gated site, all with `name: webstation-test`) — logging into that
        target happens only once (the first tab opened for it starts the session), not once per
        team_id, since a slow first login (still mid-navigation) getting hit with a second,
        third, fourth concurrent login() attempt on the very same tab is what caused
        connection-aborted/tab-not-debuggable cascades before this was fixed. But each team_id
        still only opens its *own* pinned tab (`target["tab"]`) here — not every tab the shared
        target happens to declare via `tab_count` — so warming up team "3" alone opens exactly
        one tab, not that target's whole tab range (which would otherwise silently also open
        teams "1"/"2"/"4"/"5"'s tabs as a side effect of sharing one target name).

        `team_ids`, if given, limits this to only those teams (e.g. so an operator can warm up
        just the teams they're actively working on) — unlisted teams simply aren't proactively
        opened; they still work fine, `capture()`'s own `ensure_tab()` call opens/logs into a
        team lazily on its first real request either way."""
        results = {}
        if not self.targets.enabled:
            return results
        selected = {str(t) for t in team_ids} if team_ids else None

        by_target_name = {}
        for team_id, target in self.targets.targets.items():
            if selected is not None and str(team_id) not in selected:
                continue
            target_name = str(target.get("name", team_id))
            tab_index = int(target.get("tab", 0))
            by_target_name.setdefault(target_name, []).append((str(team_id), target, tab_index))

        for target_name, entries in by_target_name.items():
            tabs, errors = [], []
            for team_id, target, tab_index in entries:
                try:
                    tab_name, _ = self.profile_manager.ensure_tab(team_id, target, tab_index=tab_index)
                    tabs.append(tab_name)
                except Exception as exc:
                    errors.append(f"tab {tab_index}: {exc}")
            entry = {"target_name": target_name, "tabs": tabs, "errors": errors}
            for team_id, _target, _tab_index in entries:
                results[team_id] = entry
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
        # Two sub-folders per channel -- "original" (pre-watermark bytes, archived here) and
        # "watermarked" (the exact bytes sent to WeChat, archived below once rendered) -- so
        # either version can be recovered later without re-deriving one from the other.
        store_record = self.store.save_screenshot(
            f"channel_{team_id}/original", capture_result["bytes"], duration_ms=round(capture_ms)
        )

        watermark_started = time.perf_counter()
        dynamic = {
            "team_id": team_id,
            "target_name": target_name,
            "user_id": user_id or "",
            "page_title": page.get("title", ""),
            "page_url": page.get("url", ""),
            "capture_ms": f"{capture_ms:.0f}",
        }
        overrides = self.watermark_settings.get_overrides(team_id)
        # Building a fresh renderer per capture is cheap (it's a stateless wrapper around a
        # dict; the font is loaded per apply() call regardless) and keeps a team's overrides
        # from ever leaking into another team's capture, since nothing is shared/mutated on
        # self.watermark itself.
        watermark = (
            WatermarkRenderer(resolve_watermark_config(self.watermark_config, overrides))
            if overrides
            else self.watermark
        )
        watermark_info = watermark.apply(raw_path, final_path, dynamic)
        watermark_ms = (time.perf_counter() - watermark_started) * 1000.0
        watermarked_store_record = self.store.save_screenshot(
            f"channel_{team_id}/watermarked", final_path.read_bytes(), duration_ms=round(capture_ms)
        )
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
            "watermarked_store_path": str(watermarked_store_record.file_path),
            "capture_ms": capture_ms,
            "watermark_ms": watermark_ms,
            **watermark_info,
        }

    def describe_watermark(self, team_id):
        """Current field values + opacity for one team, resolved base config + overrides, for
        display in a chat reply (e.g. the "status" watermark command)."""
        overrides = self.watermark_settings.get_overrides(team_id)
        resolved = resolve_watermark_config(self.watermark_config, overrides)
        fields = [item for item in (resolved.get("fields") or []) if isinstance(item, dict)]
        return {
            "team_id": str(team_id),
            "fields": [{"label": item.get("label", ""), "value": item.get("value", "")} for item in fields],
            "background_opacity": int(resolved.get("background_opacity", 190)),
            "customized": bool(overrides),
        }

    def set_watermark_field(self, team_id, field_index, value):
        fields = self.watermark_config.get("fields") or []
        if not 0 <= field_index < len(fields):
            raise IndexError(f"watermark field {field_index + 1} does not exist (channel has {len(fields)})")
        self.watermark_settings.set_field_value(team_id, field_index, value)

    def set_watermark_opacity(self, team_id, opacity):
        self.watermark_settings.set_opacity(team_id, opacity)

    def reset_watermark(self, team_id):
        self.watermark_settings.reset(team_id)
