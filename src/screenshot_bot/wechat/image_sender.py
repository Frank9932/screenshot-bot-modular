import time

from .official_api import AccessTokenInvalidError, WeChatOfficialClient


class WeChatImageSender:
    def __init__(self, appid, appsecret, client=None):
        self.client = client or WeChatOfficialClient(appid, appsecret)

    def send_image_file(self, touser, image_path):
        if not touser:
            raise RuntimeError("touser missing: FromUserName is empty")
        try:
            upload, send_result, timings = self._upload_and_send(touser, image_path, force_refresh=False)
        except AccessTokenInvalidError:
            # Token was rejected server-side despite our cache believing it was
            # still valid (e.g. revoked early). Force one fresh token and retry once.
            upload, send_result, timings = self._upload_and_send(touser, image_path, force_refresh=True)
        return {
            "media_id": upload.get("media_id", ""),
            "upload_response": upload,
            "send_response": send_result,
            "token_ms": round(timings["token_ms"], 1),
            "upload_ms": round(timings["upload_ms"], 1),
            "send_ms": round(timings["send_ms"], 1),
        }

    def _upload_and_send(self, touser, image_path, force_refresh):
        # Timed individually (rather than one lump elapsed total) because this is the one
        # segment of the reply pipeline that isn't otherwise visible in the JSONL log --
        # capture_ms/watermark_ms cover the browser side, but a slow reply that isn't a slow
        # capture has to be spent somewhere in these three sequential WeChat API round trips,
        # and only per-call timing says which one.
        token_started = time.perf_counter()
        token = self.client.get_access_token(force_refresh=force_refresh)
        token_ms = (time.perf_counter() - token_started) * 1000.0

        upload_started = time.perf_counter()
        upload = self.client.upload_temporary_image(token, image_path)
        upload_ms = (time.perf_counter() - upload_started) * 1000.0

        media_id = upload.get("media_id")
        if not media_id:
            # The real WeChatOfficialClient always raises before returning if media_id is
            # missing (see official_api.py), so this only fires against a malformed response
            # from some other client -- fail clearly here rather than sending a customer-image
            # message with no media_id (which would just surface as an opaque KeyError today).
            raise RuntimeError(f"upload response missing media_id: {upload!r}")

        send_started = time.perf_counter()
        send_result = self.client.send_customer_image(token, touser, media_id)
        send_ms = (time.perf_counter() - send_started) * 1000.0

        return upload, send_result, {"token_ms": token_ms, "upload_ms": upload_ms, "send_ms": send_ms}

    def send_text(self, touser, content):
        if not touser:
            raise RuntimeError("touser missing: FromUserName is empty")
        try:
            send_result, timings = self._send_text(touser, content, force_refresh=False)
        except AccessTokenInvalidError:
            send_result, timings = self._send_text(touser, content, force_refresh=True)
        return {
            "send_response": send_result,
            "token_ms": round(timings["token_ms"], 1),
            "send_ms": round(timings["send_ms"], 1),
        }

    def _send_text(self, touser, content, force_refresh):
        token_started = time.perf_counter()
        token = self.client.get_access_token(force_refresh=force_refresh)
        token_ms = (time.perf_counter() - token_started) * 1000.0

        send_started = time.perf_counter()
        send_result = self.client.send_customer_text(token, touser, content)
        send_ms = (time.perf_counter() - send_started) * 1000.0

        return send_result, {"token_ms": token_ms, "send_ms": send_ms}
