"""Contract tests for wechat.image_sender.WeChatImageSender -- the module that turns a local
image path into an uploaded WeChat temporary-media id and a customer-service image send. No
real network/WeChat API call anywhere in this file: WeChatImageSender is constructed with a
fake client (its `client=` constructor param exists exactly for this)."""

import unittest
from pathlib import Path

from screenshot_bot.wechat.image_sender import WeChatImageSender
from screenshot_bot.wechat.official_api import AccessTokenInvalidError, encode_multipart


class FakeClient:
    """Stands in for WeChatOfficialClient. Each of upload/send can be scripted to raise or to
    return a canned payload, and access-token-invalid can be simulated independently of
    upload/send so the retry-once-on-invalid-token behavior can be exercised in isolation."""

    def __init__(
        self,
        upload_result=None,
        upload_exc=None,
        send_result=None,
        send_exc=None,
        invalid_token_once=False,
    ):
        self.upload_result = upload_result if upload_result is not None else {"media_id": "media-123", "errcode": 0}
        self.upload_exc = upload_exc
        self.send_result = send_result if send_result is not None else {"errcode": 0}
        self.send_exc = send_exc
        self._invalid_token_once = invalid_token_once
        self._token_calls = 0
        self.upload_calls = []
        self.send_calls = []

    def get_access_token(self, force_refresh=False):
        self._token_calls += 1
        return f"token-{self._token_calls}-refresh={force_refresh}"

    def upload_temporary_image(self, token, image_path):
        self.upload_calls.append((token, image_path))
        if self._invalid_token_once and "refresh=False" in token:
            raise AccessTokenInvalidError('{"errcode": 40001}')
        if self.upload_exc:
            raise self.upload_exc
        return self.upload_result

    def send_customer_image(self, token, touser, media_id):
        self.send_calls.append((token, touser, media_id))
        if self.send_exc:
            raise self.send_exc
        return self.send_result


class ImageSenderTests(unittest.TestCase):
    def test_successful_upload_and_send_returns_media_id_and_timings(self):
        client = FakeClient()
        sender = WeChatImageSender("appid", "secret", client=client)

        result = sender.send_image_file("open-id-1", "/tmp/fake.png")

        self.assertEqual(result["media_id"], "media-123")
        self.assertEqual(result["upload_response"]["errcode"], 0)
        self.assertEqual(result["send_response"]["errcode"], 0)
        for key in ("token_ms", "upload_ms", "send_ms"):
            self.assertIn(key, result)
        self.assertEqual(len(client.upload_calls), 1)
        self.assertEqual(len(client.send_calls), 1)

    def test_upload_failure_propagates_and_never_calls_send(self):
        client = FakeClient(upload_exc=RuntimeError("upload material failed: errcode 40004"))
        sender = WeChatImageSender("appid", "secret", client=client)

        with self.assertRaises(RuntimeError):
            sender.send_image_file("open-id-1", "/tmp/fake.png")

        self.assertEqual(len(client.send_calls), 0)

    def test_send_failure_after_successful_upload_propagates(self):
        client = FakeClient(send_exc=RuntimeError("send message failed: errcode 45015"))
        sender = WeChatImageSender("appid", "secret", client=client)

        with self.assertRaises(RuntimeError):
            sender.send_image_file("open-id-1", "/tmp/fake.png")

        # Upload genuinely succeeded before the send failed -- confirms the failure really is
        # a send-stage failure, not an upload-stage one.
        self.assertEqual(len(client.upload_calls), 1)
        self.assertEqual(len(client.send_calls), 1)

    def test_missing_touser_raises_before_touching_the_client(self):
        client = FakeClient()
        sender = WeChatImageSender("appid", "secret", client=client)

        with self.assertRaises(RuntimeError):
            sender.send_image_file("", "/tmp/fake.png")

        self.assertEqual(len(client.upload_calls), 0)

    def test_missing_image_file_raises_before_any_network_call(self):
        # image_sender.py doesn't stat the path itself -- the real client's multipart encoder
        # reads the file directly (see official_api.encode_multipart), so a missing path
        # surfaces as a clean FileNotFoundError before any HTTP request is attempted.
        missing_path = str(Path("this-file-does-not-exist-12345.png"))
        self.assertFalse(Path(missing_path).exists())

        with self.assertRaises(FileNotFoundError):
            encode_multipart({}, {"media": missing_path})

    def test_invalid_media_id_in_upload_response_raises_clean_error_not_a_bare_keyerror(self):
        # Real WeChatOfficialClient.upload_temporary_image always raises before returning if
        # media_id is missing (see official_api.py) -- this exercises the defense-in-depth path
        # for a hypothetical/fake client that skips that check. Before the fix this crashed with
        # an opaque `KeyError: 'media_id'` from deep inside _upload_and_send; it must now raise a
        # clear, diagnosable RuntimeError instead, and never call send_customer_image with a
        # missing media_id.
        client = FakeClient(upload_result={"errcode": 0})
        sender = WeChatImageSender("appid", "secret", client=client)

        with self.assertRaises(RuntimeError) as ctx:
            sender.send_image_file("open-id-1", "/tmp/fake.png")

        self.assertIn("media_id", str(ctx.exception))
        self.assertEqual(len(client.send_calls), 0)

    def test_access_token_invalid_triggers_one_retry_with_force_refresh(self):
        client = FakeClient(invalid_token_once=True)
        sender = WeChatImageSender("appid", "secret", client=client)

        result = sender.send_image_file("open-id-1", "/tmp/fake.png")

        self.assertEqual(result["media_id"], "media-123")
        # First upload attempt used the non-refreshed token and raised; the retry with a
        # forced refresh is what actually succeeded.
        self.assertEqual(len(client.upload_calls), 2)
        self.assertIn("refresh=False", client.upload_calls[0][0])
        self.assertIn("refresh=True", client.upload_calls[1][0])

    def test_sender_exception_is_a_plain_exception_not_swallowed_as_success(self):
        # Whatever the underlying failure, send_image_file must never return a result that
        # looks like success (e.g. an empty dict, or one with ok=True) -- it must raise, so a
        # caller can tell the difference and report it truthfully.
        client = FakeClient(send_exc=RuntimeError("send message failed: errcode 45015"))
        sender = WeChatImageSender("appid", "secret", client=client)

        try:
            sender.send_image_file("open-id-1", "/tmp/fake.png")
            self.fail("expected RuntimeError to propagate")
        except RuntimeError as exc:
            self.assertIn("45015", str(exc))


if __name__ == "__main__":
    unittest.main()
