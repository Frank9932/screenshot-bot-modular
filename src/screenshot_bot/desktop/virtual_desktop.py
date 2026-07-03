import json
import re
import time
from contextlib import contextmanager
from pathlib import Path


DEFAULT_CONFIG = {
    "enabled": False,
    "min_desktop": 1,
    "max_desktop": 4,
    "initial_desktop": 1,
    "state_path": "runtime/virtual-desktop-state.json",
    "lock_path": "runtime/virtual-desktop.lock",
    "lock_timeout_seconds": 30,
    "switch_key_delay_ms": 180,
    "settle_delay_ms": 700,
    "trigger_pattern": r"^\s*(\d{1,2})\s*$",
}


def parse_desktop_number(text, config=None):
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    match = re.match(str(cfg["trigger_pattern"]), text or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except (IndexError, ValueError):
        return None


class VirtualDesktopSwitcher:
    def __init__(self, config=None, base_dir=None):
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        self.base_dir = Path(base_dir or ".").resolve()

    @property
    def enabled(self):
        return bool(self.config.get("enabled", False))

    def switch_to(self, target_desktop):
        if not self.enabled:
            return {
                "enabled": False,
                "requested_desktop": int(target_desktop),
                "switched": False,
                "confidence": "disabled",
                "switch_ms": 0.0,
            }
        target = self.validate_target(target_desktop)
        current = self.validate_target(self._known_current_desktop())
        delta = target - current
        direction = "right" if delta > 0 else "left"
        key_delay = max(0.0, float(self.config["switch_key_delay_ms"]) / 1000.0)
        settle_delay = max(0.0, float(self.config["settle_delay_ms"]) / 1000.0)

        import pyautogui

        pyautogui.FAILSAFE = False
        started = time.perf_counter()
        for _ in range(abs(delta)):
            pyautogui.hotkey("win", "ctrl", direction)
            time.sleep(key_delay)
        if delta:
            time.sleep(settle_delay)
        elapsed_ms = (time.perf_counter() - started) * 1000.0

        self._write_state(
            {
                "current_desktop": target,
                "previous_desktop": current,
                "updated_at_unix": time.time(),
                "method": "win_ctrl_left_right",
            }
        )
        return {
            "enabled": True,
            "requested_desktop": target,
            "previous_desktop": current,
            "current_desktop": target,
            "steps": abs(delta),
            "direction": direction if delta else "",
            "switched": bool(delta),
            "confidence": "state_file" if delta else "already_current",
            "switch_ms": elapsed_ms,
            "state_path": str(self.state_path),
        }

    @contextmanager
    def exclusive_session(self):
        import msvcrt

        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        timeout = float(self.config["lock_timeout_seconds"])
        deadline = time.monotonic() + timeout
        with self.lock_path.open("a+b") as handle:
            while True:
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"timed out waiting for desktop switch lock: {self.lock_path}")
                    time.sleep(0.1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

    def validate_target(self, target):
        target = int(target)
        min_desktop = int(self.config["min_desktop"])
        max_desktop = int(self.config["max_desktop"])
        if target < min_desktop or target > max_desktop:
            raise ValueError(f"desktop {target} outside configured range {min_desktop}-{max_desktop}")
        return target

    @property
    def state_path(self):
        return self._resolve_path(self.config["state_path"])

    @property
    def lock_path(self):
        return self._resolve_path(self.config["lock_path"])

    def _resolve_path(self, value):
        path = Path(str(value))
        if path.is_absolute():
            return path
        return self.base_dir / path

    def _known_current_desktop(self):
        state = self._read_state()
        current = state.get("current_desktop", self.config["initial_desktop"])
        try:
            return int(current)
        except (TypeError, ValueError):
            return int(self.config["initial_desktop"])

    def _read_state(self):
        if not self.state_path.is_file():
            return {}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_state(self, state):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
