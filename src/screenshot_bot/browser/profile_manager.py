import os
import socket
import subprocess
import time
from pathlib import Path

from screenshot_bot.config import resolve_path


class BrowserProfileManager:
    def __init__(self, config_path, browser_section):
        self.config_path = config_path
        self.section = browser_section or {}

    def is_port_open(self, port, timeout=0.5):
        try:
            with socket.create_connection(("127.0.0.1", int(port)), timeout=timeout):
                return True
        except OSError:
            return False

    def ensure_running(self, team_id, target):
        port = int(target["debug_port"])
        if self.is_port_open(port):
            return {"started": False, "port": port}

        chrome_path = self._resolve_chrome_path()
        profile_dir = self._profile_dir(team_id, target)
        start_url = str(target.get("start_url", "about:blank") or "about:blank")
        profile_dir.mkdir(parents=True, exist_ok=True)

        args = [
            chrome_path,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",
            start_url,
        ]
        subprocess.Popen(
            args,
            cwd=str(Path(self.config_path).resolve().parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        deadline = time.perf_counter() + float(self.section.get("startup_timeout_seconds", 15))
        while time.perf_counter() < deadline:
            if self.is_port_open(port):
                return {
                    "started": True,
                    "port": port,
                    "profile_dir": str(profile_dir),
                    "start_url": start_url,
                }
            time.sleep(0.3)
        raise RuntimeError(f"browser target {team_id} did not open debug port {port}")

    def _profile_dir(self, team_id, target):
        name = str(target.get("name", f"team-{team_id}"))
        profile_root = resolve_path(self.config_path, self.section.get("profile_root"), "runtime/browser-profiles")
        return resolve_path(self.config_path, target.get("profile_dir"), str(profile_root / name))

    def _resolve_chrome_path(self):
        candidates = [
            self.section.get("chrome_path", ""),
            str(Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe"),
            str(Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe"),
        ]
        local_app_data = os.environ.get("LocalAppData")
        if local_app_data:
            candidates.append(str(Path(local_app_data) / "Google" / "Chrome" / "Application" / "chrome.exe"))
        for candidate in candidates:
            if candidate and Path(candidate).is_file():
                return str(Path(candidate))
        raise FileNotFoundError("Chrome executable not found")
