import json
import os
import threading
from pathlib import Path

MIN_OPACITY = 0
MAX_OPACITY = 255


class TeamWatermarkSettingsStore:
    """Per-team (browser team_id, e.g. "1"-"5") overrides on top of the global watermark
    config -- lets a team's field values / background opacity be tweaked over WeChat without
    touching config.json or affecting any other team. Persisted as one small JSON file so
    overrides survive a webhook restart."""

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

    def get_overrides(self, team_id):
        return self._read().get(str(team_id)) or {}

    def set_field_value(self, team_id, field_index, value):
        with self._lock:
            data = self._read()
            entry = dict(data.get(str(team_id)) or {})
            field_values = dict(entry.get("field_values") or {})
            field_values[str(field_index)] = value
            entry["field_values"] = field_values
            data[str(team_id)] = entry
            self._write(data)

    def set_opacity(self, team_id, opacity):
        opacity = int(opacity)
        if not MIN_OPACITY <= opacity <= MAX_OPACITY:
            raise ValueError(f"opacity must be between {MIN_OPACITY} and {MAX_OPACITY}")
        with self._lock:
            data = self._read()
            entry = dict(data.get(str(team_id)) or {})
            entry["background_opacity"] = opacity
            data[str(team_id)] = entry
            self._write(data)

    def reset(self, team_id):
        with self._lock:
            data = self._read()
            if str(team_id) in data:
                del data[str(team_id)]
                self._write(data)


def resolve_watermark_config(base_config, overrides):
    """Merge a team's stored overrides onto the global watermark config for one capture.
    Field labels always come from the base config -- only a field's value can be overridden,
    so a team customizes what a row says without needing to know/retype its label."""
    if not overrides:
        return base_config
    resolved = dict(base_config)

    if "background_opacity" in overrides:
        resolved["background_opacity"] = overrides["background_opacity"]

    field_values = overrides.get("field_values") or {}
    if field_values:
        base_fields = base_config.get("fields") or []
        new_fields = []
        for index, item in enumerate(base_fields):
            if not isinstance(item, dict):
                new_fields.append(item)
                continue
            entry = dict(item)
            override_value = field_values.get(str(index))
            if override_value is not None:
                entry["value"] = override_value
            new_fields.append(entry)
        resolved["fields"] = new_fields

    return resolved
