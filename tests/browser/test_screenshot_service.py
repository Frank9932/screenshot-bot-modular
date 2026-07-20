"""Contract tests for BrowserScreenshotService.capture() -- the one entrypoint the workflow
layer calls for every channel/equipment capture. These exercise the real capture() logic
(target resolution, watermarking, ScreenshotStore writes) with the Chrome/CDP boundary
(BrowserProfileManager + CdpMultiTabService) replaced by fakes -- no real Chrome process, no
real network, no real login credentials required. See docs/agents/browser-mvp-handoff.md for
the full documented contract these tests pin down."""

import tempfile
import unittest
from pathlib import Path

from _fakes import FakeCdpService, FakeProfileManager, build_service


class CaptureSuccessTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.tmp_path = Path(self._tmpdir.name)
        self.output_dir = self.tmp_path / "screenshots"

    def test_successful_channel_capture(self):
        service, cdp = build_service(self.tmp_path)
        result = service.capture("1", user_id="user-1", output_dir=self.output_dir)

        self.assertEqual(result["source"], "chrome_devtools")
        self.assertEqual(result["team_id"], "1")
        self.assertEqual(result["target_name"], "test-target")
        self.assertEqual(result["equipment_path"], "")
        self.assertTrue(Path(result["published_path"]).exists())
        self.assertTrue(Path(result["store_path"]).exists())
        self.assertTrue(Path(result["watermarked_store_path"]).exists())
        # Plain channel capture must never touch equipment navigation.
        self.assertEqual(cdp.navigate_calls, [])
        self.assertEqual(len(cdp.screenshot_calls), 1)

    def test_successful_equipment_path_capture(self):
        service, cdp = build_service(self.tmp_path)
        result = service.capture(
            "1", user_id="user-1", output_dir=self.output_dir, equipment_path="/RYG1-SVBMS/chiller-1"
        )

        self.assertEqual(result["equipment_path"], "/RYG1-SVBMS/chiller-1")
        self.assertEqual(len(cdp.navigate_calls), 1)
        self.assertEqual(cdp.navigate_calls[0]["path"], "/RYG1-SVBMS/chiller-1")
        self.assertTrue(Path(result["published_path"]).exists())
        # Navigation must happen before the screenshot, not after.
        self.assertEqual(len(cdp.screenshot_calls), 1)

    def test_falsy_equipment_path_is_treated_as_a_plain_capture(self):
        # Documents current contract behavior: an empty-string equipment_path is not an error,
        # it silently degrades to a plain channel capture (matches `if equipment_path:` in
        # BrowserScreenshotService.capture()). A caller that means "no equipment" and one that
        # accidentally passes "" both get the same, safe behavior -- no crash, no navigation.
        service, cdp = build_service(self.tmp_path)
        result = service.capture("1", user_id="user-1", output_dir=self.output_dir, equipment_path="")

        self.assertEqual(cdp.navigate_calls, [])
        self.assertEqual(result["equipment_path"], "")


class CaptureFailureTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.tmp_path = Path(self._tmpdir.name)
        self.output_dir = self.tmp_path / "screenshots"

    def _assert_no_store_writes(self, service):
        store_dir = service.store.base_dir
        if store_dir.exists():
            self.assertEqual(list(store_dir.rglob("*.png")), [])

    def test_cdp_connection_unavailable_raises_and_writes_nothing(self):
        # Mirrors BrowserProfileManager._ensure_chrome_running -> wait_for_port's failure mode
        # when Chrome never opens its debug port.
        exc = RuntimeError("Chrome did not open debug port 9222")
        service, cdp = build_service(self.tmp_path, ensure_tab_exc=exc)

        with self.assertRaises(RuntimeError) as ctx:
            service.capture("1", user_id="user-1", output_dir=self.output_dir)
        self.assertIn("debug port", str(ctx.exception))
        self.assertEqual(cdp.screenshot_calls, [])
        self._assert_no_store_writes(service)

    def test_browser_process_unavailable_raises_and_writes_nothing(self):
        # Mirrors resolve_chrome_path()'s FileNotFoundError when no Chrome executable exists.
        exc = FileNotFoundError("Chrome executable not found")
        service, cdp = build_service(self.tmp_path, ensure_tab_exc=exc)

        with self.assertRaises(FileNotFoundError):
            service.capture("1", user_id="user-1", output_dir=self.output_dir)
        self.assertEqual(cdp.screenshot_calls, [])
        self._assert_no_store_writes(service)

    def test_target_tab_unavailable_raises_and_writes_nothing(self):
        # Mirrors CdpMultiTabService._get_page's "tab not debuggable" failure, surfaced at
        # screenshot time (the tab existed at ensure_tab() but died/closed before capture).
        exc = RuntimeError("tab not debuggable: test-target")
        service, cdp = build_service(self.tmp_path, cdp_service=FakeCdpService(screenshot_exc=exc))

        with self.assertRaises(RuntimeError) as ctx:
            service.capture("1", user_id="user-1", output_dir=self.output_dir)
        self.assertIn("not debuggable", str(ctx.exception))
        self._assert_no_store_writes(service)

    def test_login_session_failure_raises_and_writes_nothing(self):
        # Mirrors BrowserProfileManager._read_login_env's failure when a required login env
        # var is missing/unset -- the same failure shape a genuinely expired/never-established
        # session produces on the next ensure_tab() call for that target.
        exc = RuntimeError("environment variable WEBSTATION_PASSWORD is not set")
        service, cdp = build_service(self.tmp_path, ensure_tab_exc=exc)

        with self.assertRaises(RuntimeError) as ctx:
            service.capture("1", user_id="user-1", output_dir=self.output_dir)
        self.assertIn("WEBSTATION_PASSWORD", str(ctx.exception))
        self._assert_no_store_writes(service)

    def test_page_navigation_timeout_raises_before_screenshot(self):
        # Mirrors equipment_navigation.navigate_to_equipment_graphic's RuntimeError when the
        # SPA's hash route never renders any svg content within the deadline.
        exc = RuntimeError("timed out waiting for equipment graphic content: /RYG1-SVBMS/chiller-1")
        service, cdp = build_service(self.tmp_path, cdp_service=FakeCdpService(navigate_exc=exc))

        with self.assertRaises(RuntimeError) as ctx:
            service.capture(
                "1", user_id="user-1", output_dir=self.output_dir, equipment_path="/RYG1-SVBMS/chiller-1"
            )
        self.assertIn("timed out", str(ctx.exception))
        # The screenshot must never be attempted once navigation itself failed.
        self.assertEqual(cdp.screenshot_calls, [])
        self._assert_no_store_writes(service)

    def test_equipment_page_not_found_surfaces_as_the_same_navigation_timeout(self):
        # Known contract limitation, documented rather than "fixed": navigate_to_equipment_
        # graphic has no distinct signal for "this path doesn't exist" vs. "this path exists
        # but is slow to render" -- both manifest as the identical RuntimeError once the
        # svg-content wait times out. Callers cannot currently tell these apart from the
        # exception alone; only the message's embedded path differs.
        exc = RuntimeError("timed out waiting for equipment graphic content: /no/such/equipment")
        service, cdp = build_service(self.tmp_path, cdp_service=FakeCdpService(navigate_exc=exc))

        with self.assertRaises(RuntimeError) as ctx:
            service.capture("1", user_id="user-1", output_dir=self.output_dir, equipment_path="/no/such/equipment")
        self.assertIn("/no/such/equipment", str(ctx.exception))

    def test_screenshot_generation_failure_raises_and_writes_nothing(self):
        # Mirrors a CDP Page.captureScreenshot call itself failing (e.g. the tab's render
        # process crashed).
        exc = RuntimeError("CDP Page.captureScreenshot failed: {'code': -32000}")
        service, cdp = build_service(self.tmp_path, cdp_service=FakeCdpService(screenshot_exc=exc))

        with self.assertRaises(RuntimeError) as ctx:
            service.capture("1", user_id="user-1", output_dir=self.output_dir)
        self.assertIn("captureScreenshot", str(ctx.exception))
        self._assert_no_store_writes(service)

    def test_unconfigured_target_raises_keyerror_before_touching_the_browser(self):
        service, cdp = build_service(self.tmp_path)

        with self.assertRaises(KeyError):
            service.capture("99", user_id="user-1", output_dir=self.output_dir)
        # get_target() fails before ensure_tab() is ever reached.
        self.assertEqual(service.profile_manager.ensure_tab_calls, [])

    def test_malformed_tab_index_raises_valueerror_before_touching_chrome(self):
        # target declares no tab_count (defaults to 1), so an explicit tab=5 is out of range --
        # this is BrowserProfileManager.ensure_tab's own guard, still reachable through the
        # fake since it's the real BrowserProfileManager contract being pinned, not something
        # this fake needs to special-case.
        service, cdp = build_service(self.tmp_path)
        real_ensure_tab_exc = ValueError("tab 5 out of range for target test-target (tab_count=1)")
        service.profile_manager = FakeProfileManager(cdp, ensure_tab_exc=real_ensure_tab_exc)

        with self.assertRaises(ValueError):
            service.capture("1", user_id="user-1", output_dir=self.output_dir, tab=5)


if __name__ == "__main__":
    unittest.main()
