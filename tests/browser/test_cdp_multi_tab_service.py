"""Unit tests for cdp_multi_tab_service.launch_chrome's constructed argument list. No real
Chrome process is started -- subprocess.Popen is mocked so this only inspects the args."""

import tempfile
import unittest
from unittest import mock

from screenshot_bot.browser.cdp_multi_tab_service import launch_chrome


class LaunchChromeArgsTests(unittest.TestCase):
    def _launch_args(self, **kwargs):
        with tempfile.TemporaryDirectory() as profile_dir, mock.patch(
            "screenshot_bot.browser.cdp_multi_tab_service.resolve_chrome_path",
            return_value="C:\\fake\\chrome.exe",
        ), mock.patch("screenshot_bot.browser.cdp_multi_tab_service.subprocess.Popen") as popen:
            launch_chrome(9221, profile_dir, **kwargs)
        return popen.call_args[0][0]

    def test_disables_occluded_tab_render_throttling(self):
        # Real-environment finding (Live Validation, 2026-07-20): the first Page.captureScreenshot
        # on a tab that had only ever been logged into (never screenshotted) reliably timed out at
        # the configured capture_timeout_seconds, while every later capture on that same tab
        # finished in well under a second. Root cause: Chrome throttles the compositor of any tab
        # that isn't the foreground one, and a multi-team deployment keeps 4+ tabs occluded at all
        # times. These flags keep every tab rendering at full rate regardless of focus/occlusion.
        args = self._launch_args()
        for flag in (
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--disable-background-timer-throttling",
        ):
            self.assertIn(flag, args, f"missing {flag} in Chrome launch args: {args}")

    def test_still_sets_core_flags(self):
        args = self._launch_args(headless=True, ignore_certificate_errors=True)
        self.assertIn("--remote-debugging-port=9221", args)
        self.assertIn("--headless=new", args)
        self.assertIn("--ignore-certificate-errors", args)


if __name__ == "__main__":
    unittest.main()
