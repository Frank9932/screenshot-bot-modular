"""Unit tests for equipment_navigation.navigate_to_equipment_graphic -- the pure hash-route +
render-wait sequence BrowserScreenshotService.capture(equipment_path=...) depends on. Uses a
fake DevTools client (just records/answers Runtime.evaluate calls), so no real Chrome/CDP
connection is needed."""

import json
import unittest
from unittest import mock

from screenshot_bot.browser.equipment_navigation import navigate_to_equipment_graphic


class FakeDevToolsClient:
    """Answers Runtime.evaluate calls: the svg-count poll script returns each of
    `svg_counts` in turn (repeating the last value once exhausted); every other script just
    records the call and returns a truthy value."""

    def __init__(self, svg_counts):
        self._svg_counts = list(svg_counts)
        self.calls = []

    def call(self, method, params=None):
        params = params or {}
        self.calls.append((method, params))
        expression = params.get("expression", "")
        if "querySelectorAll('svg').length" in expression:
            value = self._svg_counts.pop(0) if self._svg_counts else 0
            return {"result": {"value": value}}
        return {"result": {"value": True}}


class NavigateToEquipmentGraphicTests(unittest.TestCase):
    def test_navigates_and_waits_for_svg_content_then_resizes(self):
        client = FakeDevToolsClient(svg_counts=[3])
        navigate_to_equipment_graphic(client, "/RYG1-SVBMS/chiller-1", settle_seconds=0)

        methods = [method for method, _ in client.calls]
        self.assertIn("Runtime.evaluate", methods)
        hash_call = next(p for m, p in client.calls if "window.location.hash" in p.get("expression", ""))
        self.assertEqual(hash_call["expression"], 'window.location.hash = "/RYG1-SVBMS/chiller-1";')
        resize_call = next(p for m, p in client.calls if "layout-pane-primary" in p.get("expression", ""))
        self.assertIn("12%", resize_call["expression"])

    def test_raises_runtime_error_when_svg_never_renders(self):
        client = FakeDevToolsClient(svg_counts=[])  # always reports 0
        with mock.patch("screenshot_bot.browser.equipment_navigation.time.sleep"):
            with self.assertRaises(RuntimeError) as ctx:
                navigate_to_equipment_graphic(client, "/no/such/equipment", timeout_seconds=0.01)
        self.assertIn("/no/such/equipment", str(ctx.exception))

    def test_path_with_special_characters_is_safely_json_escaped(self):
        # A malformed/hostile path (quotes, backslashes) must never break out of the JS string
        # literal it's embedded in -- json.dumps is what guarantees that.
        malformed_path = 'a"; alert(1); var x = "\\evil'
        client = FakeDevToolsClient(svg_counts=[1])
        navigate_to_equipment_graphic(client, malformed_path, settle_seconds=0)

        hash_call = next(p for m, p in client.calls if "window.location.hash" in p.get("expression", ""))
        self.assertEqual(hash_call["expression"], f"window.location.hash = {json.dumps(malformed_path)};")
        # The literal path text must only ever appear inside the json.dumps-escaped form.
        self.assertNotIn('hash = a"; alert', hash_call["expression"])

    def test_empty_string_path_still_runs_the_normal_sequence(self):
        # navigate_to_equipment_graphic itself has no falsy-path short-circuit -- that guard
        # lives one layer up, in BrowserScreenshotService.capture()'s `if equipment_path:`
        # check (see test_screenshot_service.py). Called directly with "", this still attempts
        # a real (if useless) hash navigation rather than silently doing nothing.
        client = FakeDevToolsClient(svg_counts=[1])
        navigate_to_equipment_graphic(client, "", settle_seconds=0)
        hash_call = next(p for m, p in client.calls if "window.location.hash" in p.get("expression", ""))
        self.assertEqual(hash_call["expression"], 'window.location.hash = "";')


if __name__ == "__main__":
    unittest.main()
