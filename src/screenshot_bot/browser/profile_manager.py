import os
from urllib.parse import urlparse

from screenshot_bot.config import resolve_path

from .cdp_multi_tab_service import CdpMultiTabService, launch_chrome, wait_for_port
from .devtools_client import http_json


def _origin(url):
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


class BrowserProfileManager:
    """Owns one shared Chrome process (single DevTools port, single profile dir) and the
    named-tab lifecycle on top of it via CdpMultiTabService. Every team_id gets its own tab
    in that one process instead of its own Chrome process/port. A target may also open more
    than one tab of itself (`tab_count`); only tab 0 drives login/keep-alive/refresh, since
    every tab in the process already shares its cookie jar."""

    def __init__(self, config_path, browser_section):
        self.config_path = config_path
        self.section = browser_section or {}
        self.port = int(self.section.get("debug_port", 9222))
        self.chrome_path = self.section.get("chrome_path") or None
        self.startup_timeout_seconds = float(self.section.get("startup_timeout_seconds", 15))
        self.ignore_certificate_errors = bool(self.section.get("ignore_certificate_errors", False))
        self.profile_dir = resolve_path(
            self.config_path, self.section.get("profile_dir"), "runtime/browser-profiles/shared"
        )
        self.service = CdpMultiTabService(port=self.port, max_tabs=self.section.get("max_tabs"))
        self._login_applied = set()
        self._closed_default_tabs = False

    def tab_count(self, target):
        return max(1, int(target.get("tab_count", 1)))

    def ensure_tab(self, team_id, target, tab_index=0):
        target_name = str(target.get("name") or f"team-{team_id}")
        if not 0 <= tab_index < self.tab_count(target):
            raise ValueError(f"tab {tab_index} out of range for target {target_name} (tab_count={self.tab_count(target)})")

        startup_info = self._ensure_chrome_running()
        tab_name = target_name if tab_index == 0 else f"{target_name}_tab{tab_index}"
        if not self.service.has_tab(tab_name):
            if tab_index == 0:
                url = str(target.get("start_url", "about:blank") or "about:blank")
            else:
                url = str(target.get("app_url") or target.get("start_url", "about:blank") or "about:blank")
            # If this process restarted while Chrome kept running, a tab for this target may
            # already be open (and possibly already logged in) from before — adopt it instead
            # of opening a duplicate, since some login-gated sites allow only one active
            # session per account and a second login attempt on a new tab would be rejected.
            origin = _origin(url)
            adopted = self.service.adopt_tab(tab_name, origin) if origin else None
            if not adopted:
                self.service.add_tab(tab_name, url)
            # Chrome opens its own default "New Tab" on a fresh launch, since launch_chrome()
            # passes no start URL. Closing it must happen AFTER our own first tab exists, not
            # before: closing a browser's only remaining tab quits the whole Chrome process, so
            # doing this before add_tab()/adopt_tab() above would kill Chrome instead of just
            # tidying up its startup tab.
            if not self._closed_default_tabs:
                self.service.close_untracked_tabs()
                self._closed_default_tabs = True
        # Tracked separately from has_tab(): if _apply_login() raises (e.g. a missing login env
        # var), the tab already exists in self.service by this point, but must NOT be treated as
        # "handled" — otherwise every later call would skip _apply_login forever (since the tab
        # already exists) and silently screenshot the unauthenticated login page with no error.
        if tab_index == 0 and tab_name not in self._login_applied:
            self._apply_login(tab_name, target)
            self._login_applied.add(tab_name)
        return tab_name, startup_info

    def _ensure_chrome_running(self):
        if self._is_port_open():
            return {"started": False, "port": self.port}
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        launch_chrome(
            self.port,
            self.profile_dir,
            chrome_path=self.chrome_path,
            ignore_certificate_errors=self.ignore_certificate_errors,
        )
        wait_for_port(self.port, timeout_seconds=self.startup_timeout_seconds)
        return {"started": True, "port": self.port, "profile_dir": str(self.profile_dir)}

    def _is_port_open(self):
        try:
            http_json(f"http://127.0.0.1:{self.port}/json/version", timeout=1)
            return True
        except OSError:
            return False

    def _apply_login(self, tab_name, target):
        """Run once, right when a target's tab 0 is first created (not on every capture()), so a
        login-gated target logs in on tab creation and stays authenticated for every later
        capture — matching the pattern proven in scripts/run_cdp_webstation_demo.py. Tabs opened
        afterward (tab_index > 0, same target) reuse this session automatically; they don't call
        login()/keep_alive()/refresh() themselves."""
        login_config = target.get("login") or {}
        if not login_config.get("enabled"):
            return
        username = self._read_login_env(login_config, "username_env")
        password = self._read_login_env(login_config, "password_env")
        login_kwargs = {
            key: login_config[key]
            for key in ("username_selector", "password_selector", "submit_selector")
            if login_config.get(key)
        }
        self.service.login(tab_name, username, password, **login_kwargs)

        keep_alive_interval = login_config.get("keep_alive_interval_seconds")
        if keep_alive_interval:
            self.service.start_keep_alive(tab_name, interval_seconds=float(keep_alive_interval))

        refresh_interval = login_config.get("refresh_interval_seconds")
        if refresh_interval:
            self.service.start_auto_refresh(tab_name, interval_seconds=float(refresh_interval))

    def _read_login_env(self, login_config, key):
        env_name = login_config.get(key)
        if not env_name:
            raise RuntimeError(f"browser target login config missing {key}")
        value = os.environ.get(env_name)
        if not value:
            raise RuntimeError(f"environment variable {env_name} is not set")
        return value
