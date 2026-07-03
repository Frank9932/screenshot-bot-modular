import time

from .official_api import WeChatOfficialClient


class WeChatImageSender:
    def __init__(self, appid, appsecret, client=None):
        self.client = client or WeChatOfficialClient(appid, appsecret)

    def send_image_file(self, touser, image_path):
        if not touser:
            raise RuntimeError("touser missing: FromUserName is empty")
        started = time.perf_counter()
        token = self.client.get_access_token()
        upload = self.client.upload_temporary_image(token, image_path)
        send_result = self.client.send_customer_image(token, touser, upload["media_id"])
        return {
            "media_id": upload.get("media_id", ""),
            "upload_response": upload,
            "send_response": send_result,
            "send_ms": round((time.perf_counter() - started) * 1000.0, 1),
        }
