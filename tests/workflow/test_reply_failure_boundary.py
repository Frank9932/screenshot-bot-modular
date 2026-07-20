"""Workflow-boundary test: a storage or WeChat-sender failure during
WeChatImageReplyWorkflow.handle() -- the exact entrypoint the live webhook calls per message --
must be reported as a truthful ok=False result, never as ok=True, and must never propagate out
of .handle() (which would otherwise only be contained by WeChatWebhookServer's own outer
try/except one layer further out, losing all the rich capture/storage stage context gathered so
far -- see docs/agents/storage-reply-mvp-handoff.md, "Bugs Fixed"). No real WeChat API, network,
Chrome, or production runtime directories are used anywhere in this file."""

import json
import tempfile
import time
import unittest
from pathlib import Path

from PIL import Image

from screenshot_bot.workflow.wechat_image_reply import WeChatImageReplyWorkflow


class FakeTargets:
    def __init__(self, channel_ids):
        self.enabled = True
        self.targets = {cid: {} for cid in channel_ids}

    @property
    def visible_targets(self):
        return self.targets


class FakeBrowser:
    """capture() either raises (simulating a browser/CDP or storage-layer failure bubbling up
    through capture(), which is how a ScreenshotStore write failure would actually surface --
    see BrowserScreenshotService.capture() calling self.store.save_screenshot() unguarded) or
    returns a successful capture_info dict pointing at a real temp PNG on disk."""

    def __init__(self, capture_exc=None, published_path=None):
        self.targets = FakeTargets({"1"})
        self._capture_exc = capture_exc
        self._published_path = published_path
        self.capture_calls = []

    def capture(self, *args, **kwargs):
        self.capture_calls.append((args, kwargs))
        if self._capture_exc:
            raise self._capture_exc
        return {
            "published_path": str(self._published_path),
            "capture_ms": 42.0,
        }


class FailingSender:
    """Stands in for WeChatImageSender with send_image_file always raising -- exercises the
    "sender exception containment" requirement without touching the real WeChat API."""

    def __init__(self, send_exc):
        self._send_exc = send_exc
        self.sent_texts = []
        self.send_attempts = []

    def send_text(self, touser, text):
        self.sent_texts.append((touser, text))
        return {"send_response": {}, "token_ms": 0.0, "send_ms": 0.0}

    def send_image_file(self, touser, path):
        self.send_attempts.append((touser, path))
        raise self._send_exc


def _build_workflow(tmp_path, browser, image_sender):
    config = {
        "wechat_official_webhook": {"user_team_tracker_path": "runtime/user-team-tracker.json"},
        "equipment_catalog": {"enabled": False},
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    return WeChatImageReplyWorkflow(
        str(config_path),
        image_sender,
        browser,
        screenshot_dir=tmp_path / "screenshots",
        media_downloader=None,
        incoming_image_store=None,
    )


def _text_message(touser):
    return {"MsgType": "text", "Content": "1", "FromUserName": touser, "MsgId": "1", "CreateTime": 1}


class ReplyFailureBoundaryTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.tmp_path = Path(self._tmpdir.name)

        published_path = self.tmp_path / "published.png"
        Image.new("RGB", (2, 2), (1, 2, 3)).save(published_path, "PNG")
        self.published_path = published_path

    def test_sender_failure_after_successful_capture_is_reported_honestly_not_as_success(self):
        browser = FakeBrowser(published_path=self.published_path)
        sender = FailingSender(RuntimeError("send message failed: errcode 45015"))
        workflow = _build_workflow(self.tmp_path, browser, sender)

        # Must not raise -- a send failure must never escape .handle() and crash/terminate the
        # caller (in production, the webhook's per-message processing thread).
        result = workflow.handle(_text_message("user-1"), received_at="2026-07-20T00:00:00Z", started=time.perf_counter())

        self.assertFalse(result["ok"])
        self.assertIn("45015", result["send_error"])
        # The capture stage genuinely succeeded and that truth must survive alongside the
        # send-stage failure -- distinguishing "capture worked, send failed" from any other
        # failure shape is exactly the point of this test.
        self.assertEqual(result["trigger_kind"], "browser_target")
        self.assertEqual(result["screenshot_path"], str(self.published_path))
        self.assertEqual(len(browser.capture_calls), 1)
        self.assertEqual(len(sender.send_attempts), 1)

    def test_sender_failure_on_capture_error_placeholder_is_also_reported_honestly(self):
        # Double failure: the browser/CDP capture itself fails *and* sending the resulting
        # placeholder image also fails. Both truths must be preserved, and it must still not
        # raise out of .handle().
        capture_exc = RuntimeError("Chrome did not open debug port 9222")
        browser = FakeBrowser(capture_exc=capture_exc)
        sender = FailingSender(RuntimeError("send message failed: errcode 45015"))
        workflow = _build_workflow(self.tmp_path, browser, sender)

        result = workflow.handle(_text_message("user-2"), received_at="2026-07-20T00:00:00Z", started=time.perf_counter())

        self.assertFalse(result["ok"])
        self.assertIn("debug port", result["capture_error"])
        self.assertEqual(result["trigger_kind"], "capture_error")
        self.assertIn("45015", result["send_error"])
        self.assertEqual(len(sender.send_attempts), 1)

    def test_storage_layer_failure_surfacing_through_capture_is_still_contained(self):
        # ScreenshotStore.save_screenshot() is called unguarded inside the real capture()
        # (BrowserScreenshotService.capture -> self.store.save_screenshot), so a storage write
        # failure (e.g. disk full / permission denied) reaches _run_capture the same way any
        # other capture() exception does. This pins that a storage-specific failure type is
        # handled by the same controlled containment path, with the placeholder still actually
        # sent to the user.
        storage_exc = PermissionError("Access is denied: storage/screenshots/user-3/channel_1/original")
        browser = FakeBrowser(capture_exc=storage_exc)
        sender_ok = _OneShotSuccessSender()
        workflow = _build_workflow(self.tmp_path, browser, sender_ok)

        result = workflow.handle(_text_message("user-3"), received_at="2026-07-20T00:00:00Z", started=time.perf_counter())

        self.assertTrue(result["ok"])
        self.assertEqual(result["trigger_kind"], "capture_error")
        self.assertIn("Access is denied", result["capture_error"])
        self.assertEqual(len(sender_ok.sent_images), 1)


class _OneShotSuccessSender:
    def __init__(self):
        self.sent_images = []

    def send_text(self, touser, text):
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


if __name__ == "__main__":
    unittest.main()
