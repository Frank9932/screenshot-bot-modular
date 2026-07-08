import time

from .official_api import AccessTokenInvalidError, WeChatOfficialClient


class WeChatImageSender:
    def __init__(self, appid, appsecret, client=None):
        self.client = client or WeChatOfficialClient(appid, appsecret)

    def send_image_file(self, touser, image_path):
        if not touser:
            raise RuntimeError("touser missing: FromUserName is empty")
        started = time.perf_counter()
        try:
            upload, send_result = self._upload_and_send(touser, image_path, force_refresh=False)
        except AccessTokenInvalidError:
            # Token was rejected server-side despite our cache believing it was
            # still valid (e.g. revoked early). Force one fresh token and retry once.
            upload, send_result = self._upload_and_send(touser, image_path, force_refresh=True)
        return {
            "media_id": upload.get("media_id", ""),
            "upload_response": upload,
            "send_response": send_result,
            "send_ms": round((time.perf_counter() - started) * 1000.0, 1),
        }

    def _upload_and_send(self, touser, image_path, force_refresh):
        token = self.client.get_access_token(force_refresh=force_refresh)
        upload = self.client.upload_temporary_image(token, image_path)
        send_result = self.client.send_customer_image(token, touser, upload["media_id"])
        return upload, send_result

    def send_text(self, touser, content):
        if not touser:
            raise RuntimeError("touser missing: FromUserName is empty")
        started = time.perf_counter()
        try:
            send_result = self._send_text(touser, content, force_refresh=False)
        except AccessTokenInvalidError:
            send_result = self._send_text(touser, content, force_refresh=True)
        return {
            "send_response": send_result,
            "send_ms": round((time.perf_counter() - started) * 1000.0, 1),
        }

    def _send_text(self, touser, content, force_refresh):
        token = self.client.get_access_token(force_refresh=force_refresh)
        return self.client.send_customer_text(token, touser, content)
