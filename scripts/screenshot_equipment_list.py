import argparse
import csv
import json
import sys
import time
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import os

from screenshot_bot.browser import CdpMultiTabService, launch_chrome, wait_for_port
from screenshot_bot.browser.devtools_client import DevToolsWebSocket

LOGIN_URL = "https://10.121.0.14/login.html"

SVG_COUNT_SCRIPT = "document.querySelectorAll('svg').length"

# react-splitter-layout controls the bottom alarm-list pane's height via this inline style;
# shrinking it gives the equipment graphic/data tables the rest of the vertical space. The SPA
# remounts this element on every hash navigation, so it must be reapplied per equipment, not once.
RESIZE_SCRIPT = """
(function(height) {
    var el = document.querySelector('.layout-pane.layout-pane-primary');
    if (!el) return false;
    el.style.height = height;
    window.dispatchEvent(new Event('resize'));
    return true;
})(%s)
"""


def read_equipment(csv_path, category):
    rows = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if category is None or row["category"] == category:
                rows.append(row)
    return rows


def svg_count(client):
    result = client.call("Runtime.evaluate", {"expression": SVG_COUNT_SCRIPT})
    return result.get("result", {}).get("value") or 0


def wait_for_content(client, timeout=20, poll=0.5):
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if svg_count(client) > 0:
            return True
        time.sleep(poll)
    return False


def safe_filename(name):
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)


def main():
    parser = argparse.ArgumentParser(
        description="Log into the webstation once, then walk a list of equipment graphics "
        "(from a CSV produced by crawling the app's List View) and screenshot each one, "
        "with the alarm-list pane collapsed so the equipment data tables get full height."
    )
    parser.add_argument("--csv", default=str(ROOT / "runtime" / "cdp-explore-out" / "hvac_equipment.csv"))
    parser.add_argument("--category", default="RYG1 - CDU", help="filter rows by this category column; omit with --all")
    parser.add_argument("--all", action="store_true", help="ignore --category and capture every row in the CSV")
    parser.add_argument("--output-dir", default=str(ROOT / "runtime" / "cdp-screenshots" / "cdu"))
    parser.add_argument("--port", type=int, default=9335)
    parser.add_argument("--profile-dir", default=str(ROOT / "runtime" / "cdp-explore-profile"))
    parser.add_argument("--pane-height", default="12%", help="CSS height for the collapsed alarm pane")
    parser.add_argument("--settle-seconds", type=float, default=3.0, help="wait after load for live data to populate")
    parser.add_argument("--limit", type=int, default=None, help="cap the number of items captured (for testing)")
    parser.add_argument("--names", default=None, help="comma-separated exact equipment names to retry, skips --category filtering")
    args = parser.parse_args()

    category = None if args.all else args.category
    equipment = read_equipment(args.csv, category)
    if args.names:
        wanted = {n.strip() for n in args.names.split(",") if n.strip()}
        equipment = [row for row in read_equipment(args.csv, None) if row["equipment"] in wanted]
    if args.limit:
        equipment = equipment[: args.limit]
    if not equipment:
        parser.error(f"no rows matched category={category!r} in {args.csv}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    username = os.environ["WEBSTATION_USERNAME"]
    password = os.environ["WEBSTATION_PASSWORD"]

    process = launch_chrome(args.port, args.profile_dir, ignore_certificate_errors=True)
    service = CdpMultiTabService(args.port, max_tabs=2)
    results = []
    try:
        wait_for_port(args.port)
        service.add_tab("capture", LOGIN_URL)
        try:
            login_result = service.login("capture", username, password)
            print(f"login: {login_result}")
        except Exception as error:
            # This app enforces one active session per account and issues a session-only
            # cookie; a fresh profile/process usually gets a clean login, but a stale
            # already-authenticated session can also cause the login-page-transition check
            # to time out even though the account is fine — the bootstrap wait below confirms
            # which case this actually is.
            print(f"login() raised (may still be authenticated): {error}")

        page = service._get_page("capture")
        with DevToolsWebSocket(page["webSocketDebuggerUrl"], timeout=20) as client:
            client.call("Runtime.enable")
            if not wait_for_content(client, timeout=30):
                raise RuntimeError("app did not finish bootstrapping (no svg content after 30s)")

            print(f"capturing {len(equipment)} item(s) -> {output_dir}")
            for i, row in enumerate(equipment, start=1):
                name = row["equipment"]
                path = row["path"]
                started = time.perf_counter()
                try:
                    hash_script = f"window.location.hash = {json.dumps(path)};"
                    client.call("Runtime.evaluate", {"expression": hash_script})
                    if not wait_for_content(client, timeout=35):
                        raise RuntimeError("timed out waiting for graphic content")

                    client.call("Runtime.evaluate", {
                        "expression": RESIZE_SCRIPT % json.dumps(args.pane_height)
                    })
                    time.sleep(args.settle_seconds)

                    out_path = output_dir / f"{safe_filename(name)}.png"
                    service.screenshot("capture", out_path)
                    elapsed = time.perf_counter() - started
                    print(f"[{i}/{len(equipment)}] {name}: ok ({elapsed:.1f}s) -> {out_path}")
                    results.append({"equipment": name, "ok": True, "path": str(out_path)})
                except Exception as error:
                    print(f"[{i}/{len(equipment)}] {name}: FAILED - {error}")
                    results.append({"equipment": name, "ok": False, "error": str(error)})
    finally:
        process.terminate()

    failed = [r for r in results if not r["ok"]]
    print(f"\ndone: {len(results) - len(failed)}/{len(results)} succeeded")
    if failed:
        print("failed items:", ", ".join(r["equipment"] for r in failed))


if __name__ == "__main__":
    main()
