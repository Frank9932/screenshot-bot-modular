"""Consumer-boundary test: a BrowserScreenshotService.capture() failure must never crash the
webhook process. WeChatImageReplyWorkflow._run_capture (called from .handle(), the exact
function the live webhook invokes per message) is the one place that boundary is enforced --
this test drives the real .handle() with a fake browser whose .capture() raises, and asserts
the workflow converts that into a controlled, ok=True "capture_error" result instead of letting
the exception propagate. See docs/agents/browser-mvp-handoff.md."""

import json
import tempfile
import time
import unittest
from pathlib import Path

from screenshot_bot.workflow.wechat_image_reply import WeChatImageReplyWorkflow


class FakeTargets:
    def __init__(self, channel_ids):
        self.enabled = True
        self.targets = {cid: {} for cid in channel_ids}

    @property
    def visible_targets(self):
        return self.targets


class FakeBrowser:
    def __init__(self, capture_exc):
        self.targets = FakeTargets({"1"})
        self._capture_exc = capture_exc
        self.capture_calls = []

    def capture(self, *args, **kwargs):
        self.capture_calls.append((args, kwargs))
        raise self._capture_exc


class FakeImageSender:
    def __init__(self):
        self.sent_texts = []
        self.sent_images = []

    def send_text(self, touser, text):
        self.sent_texts.append((touser, text))
        return {"send_response": {}, "token_ms": 0.0, "send_ms": 0.0}

    def send_image_file(self, touser, path):
        self.sent_images.append((touser, path))
        return {
            "media_id": "fake-media-id",
            "upload_response": {},
            "send_response": {},
            "token_ms": 0.0,
            "upload_ms": 0.0,
            "send_ms": 0.0,
        }


def _build_workflow(tmp_path, capture_exc):
    config = {
        "wechat_official_webhook": {"user_team_tracker_path": "runtime/user-team-tracker.json"},
        "equipment_catalog": {"enabled": False},
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    browser = FakeBrowser(capture_exc)
    image_sender = FakeImageSender()
    workflow = WeChatImageReplyWorkflow(
        str(config_path),
        image_sender,
        browser,
        screenshot_dir=tmp_path / "screenshots",
        media_downloader=None,
        incoming_image_store=None,
    )
    return workflow, browser, image_sender


class CaptureFailureContainmentTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.tmp_path = Path(self._tmpdir.name)

    def test_browser_capture_exception_becomes_a_controlled_capture_error_result(self):
        exc = RuntimeError("Chrome did not open debug port 9222")
        workflow, browser, image_sender = _build_workflow(self.tmp_path, exc)

        message = {
            "MsgType": "text",
            "Content": "1",
            "FromUserName": "user-1",
            "MsgId": "1",
            "CreateTime": 1,
        }

        # Must not raise -- this is the entire point of the test.
        result = workflow.handle(message, received_at="2026-07-20T00:00:00Z", started=time.perf_counter())

        self.assertTrue(result["ok"])
        self.assertEqual(result["trigger_kind"], "capture_error")
        self.assertEqual(result["response_image_kind"], "capture_error")
        self.assertIn("debug port", result["capture_error"])
        self.assertEqual(len(browser.capture_calls), 1)
        # A placeholder image must actually have been generated and "sent" -- the sender must
        # not be silently skipped just because capture failed.
        self.assertTrue(Path(result["screenshot_path"]).exists())
        self.assertEqual(len(image_sender.sent_images), 1)

    def test_various_browser_exception_types_are_all_contained(self):
        # The workflow's except Exception catches every exception type capture() can raise,
        # not just RuntimeError -- confirm a sample of the other types documented in the
        # browser capture contract don't slip through either.
        for exc in [
            FileNotFoundError("Chrome executable not found"),
            KeyError("browser target is not configured: 1"),
            ValueError("tab 5 out of range for target test-target (tab_count=1)"),
        ]:
            with self.subTest(exc_type=type(exc).__name__):
                workflow, browser, image_sender = _build_workflow(self.tmp_path, exc)
                message = {
                    "MsgType": "text",
                    "Content": "1",
                    "FromUserName": f"user-{type(exc).__name__}",
                    "MsgId": "1",
                    "CreateTime": 1,
                }
                result = workflow.handle(message, received_at="2026-07-20T00:00:00Z", started=time.perf_counter())
                self.assertTrue(result["ok"])
                self.assertEqual(result["trigger_kind"], "capture_error")


if __name__ == "__main__":
    unittest.main()
