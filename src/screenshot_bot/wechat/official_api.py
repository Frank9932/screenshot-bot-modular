import json
import mimetypes
import threading
import time
import uuid
from pathlib import Path
from urllib import parse, request

TOKEN_REFRESH_MARGIN_SECONDS = 300
INVALID_TOKEN_ERRCODES = {40001, 40014, 42001}


class AccessTokenInvalidError(RuntimeError):
    pass


class WeChatOfficialClient:
    def __init__(self, appid, appsecret):
        self.appid = appid
        self.appsecret = appsecret
        self._token_lock = threading.Lock()
        self._cached_token = None
        self._token_expires_at = 0.0

    def get_access_token(self, force_refresh=False):
        with self._token_lock:
            if not force_refresh and self._cached_token and time.monotonic() < self._token_expires_at:
                return self._cached_token
            token, expires_in = self._fetch_stable_token(force_refresh)
            self._cached_token = token
            self._token_expires_at = time.monotonic() + max(expires_in - TOKEN_REFRESH_MARGIN_SECONDS, 60)
            return token

    def _fetch_stable_token(self, force_refresh):
        # cgi-bin/stable_token is WeChat-managed: repeat calls without force_refresh
        # return the same still-valid token without consuming the daily quota, and
        # it dedupes concurrent refreshes across processes sharing one appid.
        url = "https://api.weixin.qq.com/cgi-bin/stable_token"
        payload = {
            "grant_type": "client_credential",
            "appid": self.appid,
            "secret": self.appsecret,
            "force_refresh": bool(force_refresh),
        }
        response = http_json("POST", url, payload)
        printable = dict(response)
        printable.pop("access_token", None)
        print("wechat stable_token response:", json.dumps(printable, ensure_ascii=False, separators=(",", ":")), flush=True)
        if response.get("errcode") not in [None, 0] or not response.get("access_token"):
            raise RuntimeError("access_token failed: " + json.dumps(printable, ensure_ascii=False))
        return response["access_token"], int(response.get("expires_in", 7200))

    def upload_temporary_image(self, access_token, image_path):
        url = "https://api.weixin.qq.com/cgi-bin/media/upload?access_token=" + parse.quote(access_token) + "&type=image"
        data, content_type = encode_multipart({}, {"media": image_path})
        req = request.Request(url, data=data, headers={"Content-Type": content_type}, method="POST")
        with request.urlopen(req, timeout=30) as response:
            text = response.read().decode("utf-8")
        payload = json.loads(text)
        print("wechat media upload response:", text, flush=True)
        _raise_for_invalid_token(payload)
        if payload.get("errcode") not in [None, 0] or not payload.get("media_id"):
            raise RuntimeError("upload material failed: " + text)
        return payload

    def send_customer_image(self, access_token, touser, media_id):
        url = "https://api.weixin.qq.com/cgi-bin/message/custom/send?access_token=" + parse.quote(access_token)
        payload = {"touser": touser, "msgtype": "image", "image": {"media_id": media_id}}
        result = http_json("POST", url, payload)
        print("wechat image send response:", json.dumps(result, ensure_ascii=False, separators=(",", ":")), flush=True)
        _raise_for_invalid_token(result)
        if result.get("errcode") != 0:
            raise RuntimeError("send message failed: " + json.dumps(result, ensure_ascii=False))
        return result


def _raise_for_invalid_token(payload):
    if isinstance(payload, dict) and payload.get("errcode") in INVALID_TOKEN_ERRCODES:
        raise AccessTokenInvalidError(json.dumps(payload, ensure_ascii=False))


def http_json(method, url, payload=None, timeout=20):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = request.Request(url, data=data, headers=headers, method=method)
    with request.urlopen(req, timeout=timeout) as response:
        text = response.read().decode("utf-8")
    return json.loads(text) if text else {}


def encode_multipart(fields, files):
    boundary = "----screenshotbot" + uuid.uuid4().hex
    body = bytearray()
    for name, value in fields.items():
        body.extend(("--" + boundary + "\r\n").encode("utf-8"))
        body.extend((f'Content-Disposition: form-data; name="{name}"\r\n\r\n').encode("utf-8"))
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")
    for name, path in files.items():
        file_path = Path(path)
        filename = file_path.name
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body.extend(("--" + boundary + "\r\n").encode("utf-8"))
        body.extend((f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n').encode("utf-8"))
        body.extend((f"Content-Type: {content_type}\r\n\r\n").encode("utf-8"))
        body.extend(file_path.read_bytes())
        body.extend(b"\r\n")
    body.extend(("--" + boundary + "--\r\n").encode("utf-8"))
    return bytes(body), "multipart/form-data; boundary=" + boundary
