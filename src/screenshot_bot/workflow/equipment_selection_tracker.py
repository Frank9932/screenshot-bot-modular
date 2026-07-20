import json
import os
import threading
from pathlib import Path


class EquipmentSelectionTracker:
    """Persists each WeChat user's in-progress/confirmed selection for the select-equipment
    guided flow (category -> equipment -> confirm), so a webhook restart doesn't lose where a
    sender was mid-flow. Unlike UserTeamTracker's single always-current fact, this genuinely is
    a small conversation state machine: resolving a bare digit as "equipment list item N" instead
    of "channel N" (see message_router.route_message) depends on knowing which stage a sender is
    currently in. Stages: "awaiting_category" -> "awaiting_equipment" -> "awaiting_confirm" ->
    "confirmed" (or back to Idle -- the same empty-entry state as never having started -- via
    cancel, or restarted from any stage via "设备")."""

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

    def _set(self, user_id, entry):
        with self._lock:
            data = self._read()
            data[str(user_id)] = entry
            self._write(data)

    def get(self, user_id):
        """Returns this sender's current entry ({"stage": ..., possibly "category"/"equipment"/
        "path"}), or {} if they've never started the flow."""
        entry = self._read().get(str(user_id))
        return entry if isinstance(entry, dict) else {}

    def start(self, user_id):
        self._set(user_id, {"stage": "awaiting_category"})

    def set_category(self, user_id, category):
        self._set(user_id, {"stage": "awaiting_equipment", "category": category})

    def set_pending_equipment(self, user_id, category, equipment, path):
        self._set(user_id, {"stage": "awaiting_confirm", "category": category, "equipment": equipment, "path": path})

    def confirm(self, user_id):
        entry = dict(self.get(user_id))
        entry["stage"] = "confirmed"
        self._set(user_id, entry)

    def cancel(self, user_id):
        """Resets to the same empty-entry Idle state as a sender who never started the flow --
        deliberately not a distinct "none" stage, so callers only ever need to check the real
        active stages and can treat "absent"/"cancelled" identically."""
        self._set(user_id, {})
