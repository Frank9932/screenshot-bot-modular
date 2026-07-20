import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from screenshot_bot.browser.target_config import BrowserTargetConfig
from screenshot_bot.config import get_section, load_json_config
from screenshot_bot.wechat.menu_manager import WeChatMenuManager
from screenshot_bot.workflow.menu import build_menu_payload


def main():
    parser = argparse.ArgumentParser(
        description="Push or inspect the WeChat tap-to-command menu (see src/screenshot_bot/workflow/menu.py)."
    )
    parser.add_argument("action", choices=["set", "get"], help="'set' pushes the menu built from configured channels; 'get' prints the menu currently live on the account")
    parser.add_argument("--config-path", default=str(ROOT / "config.json"))
    args = parser.parse_args()

    config_path = str(Path(args.config_path).resolve())
    config = load_json_config(config_path)
    webhook = get_section(config, "wechat_official_webhook")
    appid = os.environ.get(webhook.get("appid_env", "WECHAT_APPID"), "")
    appsecret = os.environ.get(webhook.get("appsecret_env", "WECHAT_APPSECRET"), "")
    if not appid or not appsecret:
        raise RuntimeError("WECHAT_APPID/WECHAT_APPSECRET (or their configured env var names) are required")

    manager = WeChatMenuManager(appid, appsecret)

    if args.action == "get":
        print(json.dumps(manager.get_menu(), ensure_ascii=False, indent=2))
        return

    targets = BrowserTargetConfig(config_path, config)
    equipment_enabled = bool(get_section(config, "equipment_catalog").get("enabled", False))
    menu = build_menu_payload(targets.visible_targets.keys(), equipment_enabled=equipment_enabled)
    result = manager.set_menu(menu)
    print(json.dumps({"menu": menu, "result": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
