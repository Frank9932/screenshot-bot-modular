from screenshot_bot.config import get_section, load_json_config


class BrowserTargetConfig:
    def __init__(self, config_path, config=None):
        self.config_path = config_path
        self.config = config or load_json_config(config_path)
        self.section = get_section(self.config, "browser_targets")

    @property
    def enabled(self):
        return bool(self.section.get("enabled", False))

    @property
    def targets(self):
        targets = self.section.get("targets") or {}
        return targets if isinstance(targets, dict) else {}

    @property
    def visible_targets(self):
        """Targets to advertise in help/guidance text -- excludes channels marked "backup":
        true, which still work if a sender happens to type their digit, they're just not
        mentioned so an ordinary user never stumbles onto them."""
        return {tid: t for tid, t in self.targets.items() if not t.get("backup")}

    def parse_number(self, text):
        if not self.enabled:
            return None
        value = str(text or "").strip()
        if not value.isdigit():
            return None
        return value if value in self.targets else None

    def get_target(self, team_id):
        target = self.targets.get(str(team_id))
        if not isinstance(target, dict):
            raise KeyError(f"browser target is not configured: {team_id}")
        return target
