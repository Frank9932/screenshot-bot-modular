import json
import os
import threading
from pathlib import Path

UNASSIGNED = "unassigned"
PRIVATE_CHANNEL_ID = "private"


class UserTeamTracker:
    """Remembers the most recent team_id each WeChat user selected (by sending a bare team
    digit), so an incoming photo -- which carries no team info of its own -- can still be filed
    under the team its sender was last using. Not a conversation/session state machine, just a
    last-seen lookup, persisted so it survives a webhook restart. Also remembers whether a sender
    has unlocked the (passcode-gated, otherwise hidden) private channel."""

    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def _read(self):
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (FileNotFoundError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.path)

    def _entry(self, data, user_id):
        entry = data.get(str(user_id))
        return entry if isinstance(entry, dict) else {}

    def get_team(self, user_id):
        return self._entry(self._read(), user_id).get("team") or UNASSIGNED

    def set_team(self, user_id, team_id):
        with self._lock:
            data = self._read()
            entry = self._entry(data, user_id)
            entry["team"] = str(team_id)
            data[str(user_id)] = entry
            self._write(data)

    def has_unlocked_private(self, user_id):
        return bool(self._entry(self._read(), user_id).get("private_unlocked"))

    def unlock_private(self, user_id):
        with self._lock:
            data = self._read()
            entry = self._entry(data, user_id)
            entry["private_unlocked"] = True
            data[str(user_id)] = entry
            self._write(data)
