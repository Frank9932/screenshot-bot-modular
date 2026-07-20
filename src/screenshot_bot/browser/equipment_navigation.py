"""Shared hash-route navigation + render-wait logic for this app's per-equipment graphic pages
-- the same sequence scripts/screenshot_equipment_list.py uses to batch-capture equipment
offline against a throwaway Chrome process, factored out here so the live webhook's per-request
equipment capture (see CdpMultiTabService.navigate_equipment / BrowserScreenshotService.capture's
equipment_path) can run it against an already-open, already-logged-in shared tab instead."""

import json
import time

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


def _svg_count(client):
    result = client.call("Runtime.evaluate", {"expression": SVG_COUNT_SCRIPT})
    return result.get("result", {}).get("value") or 0


def _wait_for_svg_content(client, timeout_seconds, poll_interval=0.5):
    deadline = time.perf_counter() + timeout_seconds
    while time.perf_counter() < deadline:
        if _svg_count(client) > 0:
            return True
        time.sleep(poll_interval)
    return False


def navigate_to_equipment_graphic(client, path, pane_height="12%", settle_seconds=3.0, timeout_seconds=35):
    """`client` is an already-`Runtime.enable`'d DevToolsWebSocket against the target tab.
    Raises RuntimeError if the graphic never renders (no svg content) within timeout_seconds."""
    hash_script = f"window.location.hash = {json.dumps(path)};"
    client.call("Runtime.evaluate", {"expression": hash_script})
    if not _wait_for_svg_content(client, timeout_seconds=timeout_seconds):
        raise RuntimeError(f"timed out waiting for equipment graphic content: {path}")
    client.call("Runtime.evaluate", {"expression": RESIZE_SCRIPT % json.dumps(pane_height)})
    time.sleep(settle_seconds)
