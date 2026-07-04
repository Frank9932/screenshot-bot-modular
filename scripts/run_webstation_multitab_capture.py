import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from screenshot_bot.browser import BrowserScreenshotService


def main():
    parser = argparse.ArgumentParser(
        description="Capture every tab of a multi-tab browser_targets entry through the "
        "production BrowserScreenshotService path (same call the WeChat webhook uses), "
        "logging in once on tab 0 and reusing that session for every other tab."
    )
    parser.add_argument("--config-path", default=str(ROOT / "config.example.json"))
    parser.add_argument("--team-id", default="4")
    parser.add_argument("--output-dir", default=str(ROOT / "runtime" / "webstation-multitab-demo"))
    args = parser.parse_args()

    svc = BrowserScreenshotService(args.config_path)
    target = svc.targets.get_target(args.team_id)
    tab_count = svc.profile_manager.tab_count(target)
    print(f"target={target.get('name')} tab_count={tab_count}")

    for tab in range(tab_count):
        info = svc.capture(args.team_id, tab=tab, output_dir=args.output_dir)
        print(
            f"tab {tab}: startup={info['browser_startup']} capture_ms={info['capture_ms']:.1f} "
            f"published={info['published_path']} store={info['store_path']}"
        )


if __name__ == "__main__":
    main()
