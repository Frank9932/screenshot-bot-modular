import json
from pathlib import Path


def load_json_config(path):
    with Path(path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def get_section(config, name):
    section = config.get(name) or {}
    return section if isinstance(section, dict) else {}


def resolve_path(base_file, value, default_value=""):
    selected = str(value or default_value or "")
    path = Path(selected)
    if path.is_absolute():
        return path
    return Path(base_file).resolve().parent / path
