import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from screenshot_bot.browser import CdpMultiTabService, launch_chrome, wait_for_port


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=9333)
    parser.add_argument("--output-dir", default=str(ROOT / "runtime" / "cdp-multi-tab-demo"))
    parser.add_argument("--chrome-path", default="")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    user_data_dir = output_dir / "profile"

    process = launch_chrome(args.port, user_data_dir, chrome_path=args.chrome_path or None, headless=args.headless)
    try:
        wait_for_port(args.port)
        service = CdpMultiTabService(args.port)

        service.add_tab("tab_a", "https://example.com")
        service.add_tab("tab_b", "https://example.org")
        time.sleep(1.5)

        for tab in service.list_tabs():
            print(f"tab: {tab['name']} url={tab['url']} title={tab['title']!r}")

        for name in ("tab_a", "tab_b"):
            result = service.screenshot(name, output_dir / f"{name}.png")
            print(f"{name}: {result['elapsed_ms']:.1f} ms -> {result['path']}")
    finally:
        process.terminate()


if __name__ == "__main__":
    main()
