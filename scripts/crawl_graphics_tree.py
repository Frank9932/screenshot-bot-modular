import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from screenshot_bot.browser import CdpMultiTabService, launch_chrome, wait_for_port
from screenshot_bot.browser.devtools_client import DevToolsWebSocket

BASE = "https://10.121.0.14/"
LOGIN_URL = "https://10.121.0.14/login.html"

ROWS_SCRIPT = """
(function() {
    var rows = Array.from(document.querySelectorAll('.row.large.selectable'));
    return JSON.stringify(rows.map(function(r) {
        var use = r.querySelector('svg.icon use');
        var iconHref = use ? use.getAttribute('xlink:href') : '';
        var nameEl = r.querySelector('.coml-item-row .ellipsis');
        return {
            name: nameEl ? nameEl.textContent.trim() : r.textContent.trim(),
            icon: iconHref,
            isFolder: /Folder/i.test(iconHref)
        };
    }));
})()
"""

SCROLL_SCRIPT = """
(function() {
    var el = document.querySelector('.ReactVirtualized__Grid');
    if (!el) return JSON.stringify({moved: false});
    var before = el.scrollTop;
    el.scrollTop = el.scrollTop + el.clientHeight;
    return JSON.stringify({before: before, after: el.scrollTop, moved: el.scrollTop !== before});
})()
"""

RESET_SCROLL_SCRIPT = """
(function() {
    var el = document.querySelector('.ReactVirtualized__Grid');
    if (el) el.scrollTop = 0;
    return true;
})()
"""


def get_rows(client):
    result = client.call("Runtime.evaluate", {"expression": ROWS_SCRIPT})
    value = result.get("result", {}).get("value")
    return json.loads(value) if value else []


def wait_for_rows_settle(client, timeout=15, poll=0.4):
    """Poll until row content stops changing between two consecutive reads (virtualized list
    has finished its post-navigation render), not just until it's non-empty -- an empty folder
    is a valid final state too, so waiting for "non-empty" alone would spin for the full
    timeout on every empty folder."""
    deadline = time.perf_counter() + timeout
    previous = None
    while time.perf_counter() < deadline:
        current = get_rows(client)
        if current and current == previous:
            return current
        previous = current
        time.sleep(poll)
    return previous or []


def get_all_rows(client, max_scrolls=80):
    client.call("Runtime.evaluate", {"expression": RESET_SCROLL_SCRIPT})
    time.sleep(0.2)
    collected = {}
    for _ in range(max_scrolls):
        for r in get_rows(client):
            collected[r["name"]] = r
        result = client.call("Runtime.evaluate", {"expression": SCROLL_SCRIPT})
        value = result.get("result", {}).get("value")
        info = json.loads(value) if value else {"moved": False}
        if not info.get("moved"):
            for r in get_rows(client):
                collected[r["name"]] = r
            break
        time.sleep(0.25)
    return list(collected.values())


def goto_hash(client, path):
    script = f"window.location.hash = {json.dumps(path)};"
    client.call("Runtime.evaluate", {"expression": script})
    time.sleep(0.3)
    wait_for_rows_settle(client)
    return get_all_rows(client)


def path_to_url(path):
    return BASE + "#" + quote(path, safe="")


def crawl(client, path, max_depth, depth=0, results=None, stats=None):
    if results is None:
        results = []
    if stats is None:
        stats = {"folders_visited": 0, "leaves": 0}
    if depth > max_depth:
        print(f"  {'  ' * depth}max depth reached at {path}, treating as leaf")
        results.append({"path": path, "url": path_to_url(path)})
        stats["leaves"] += 1
        return results, stats

    rows = goto_hash(client, path)
    stats["folders_visited"] += 1
    print(f"{'  ' * depth}{path}: {len(rows)} entries")
    for row in rows:
        child_path = f"{path}/{row['name']}"
        if row["isFolder"]:
            crawl(client, child_path, max_depth, depth + 1, results, stats)
        else:
            results.append({"path": child_path, "url": path_to_url(child_path)})
            stats["leaves"] += 1
    return results, stats


def main():
    parser = argparse.ArgumentParser(
        description="Recursively crawl the webstation's Graphics tree (or any subtree) via its "
        "List View, collecting every leaf item's hash path and full URL. Unlike the flat "
        "HVAC-specific crawl, this recurses to arbitrary depth since other categories "
        "(Electrical, Floor Plan, etc.) may nest more deeply than HVAC's fixed 2 levels."
    )
    parser.add_argument("--root", default="/RYG1-SVBMS/Graphics")
    parser.add_argument("--categories", default="Custom Type,Diagram,Electrical,Floor Plan,Fuel System,Panel,Space Sensor,Utility",
                         help="comma-separated child names of --root to crawl (each becomes its own CSV)")
    parser.add_argument("--output-dir", default=str(ROOT / "runtime" / "cdp-explore-out"))
    parser.add_argument("--port", type=int, default=9335)
    parser.add_argument("--profile-dir", default=str(ROOT / "runtime" / "cdp-explore-profile"))
    parser.add_argument("--max-depth", type=int, default=8)
    args = parser.parse_args()

    categories = [c.strip() for c in args.categories.split(",") if c.strip()]
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    username = os.environ["WEBSTATION_USERNAME"]
    password = os.environ["WEBSTATION_PASSWORD"]

    process = launch_chrome(args.port, args.profile_dir, ignore_certificate_errors=True)
    service = CdpMultiTabService(args.port, max_tabs=2)
    try:
        wait_for_port(args.port)
        service.add_tab("crawl", LOGIN_URL)
        try:
            login_result = service.login("crawl", username, password)
            print(f"login: {login_result}")
        except Exception as error:
            print(f"login() raised (may still be authenticated): {error}")

        page = service._get_page("crawl")
        with DevToolsWebSocket(page["webSocketDebuggerUrl"], timeout=20) as client:
            client.call("Runtime.enable")
            wait_for_rows_settle(client, timeout=30)  # let SPA bootstrap

            for category in categories:
                cat_path = f"{args.root}/{category}"
                print(f"\n=== {category} ===")
                results, stats = crawl(client, cat_path, args.max_depth)
                safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in category).strip().replace(" ", "_")
                out_path = output_dir / f"graphics_{safe_name}.csv"
                with open(out_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=["path", "url"])
                    writer.writeheader()
                    writer.writerows(results)
                print(f"{category}: {stats['leaves']} leaf items, {stats['folders_visited']} folders visited -> {out_path}")
    finally:
        process.terminate()


if __name__ == "__main__":
    main()
