import json
import mimetypes
import uuid
from pathlib import Path
from urllib import parse, request


class WeChatOfficialClient:
    def __init__(self, appid, appsecret):
        self.appid = appid
        self.appsecret = appsecret

    def get_access_token(self):
        url = (
            "https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential"
            + "&appid="
            + parse.quote(self.appid)
            + "&secret="
            + parse.quote(self.appsecret)
        )
        payload = http_json("GET", url)
        printable = dict(payload)
        printable.pop("access_token", None)
        print("wechat access_token response:", json.dumps(printable, ensure_ascii=False, separators=(",", ":")), flush=True)
        if payload.get("errcode") not in [None, 0] or not payload.get("access_token"):
            raise RuntimeError("access_token failed: " + json.dumps(printable, ensure_ascii=False))
        return payload["access_token"]

    def upload_temporary_image(self, access_token, image_path):
        url = "https://api.weixin.qq.com/cgi-bin/media/upload?access_token=" + parse.quote(access_token) + "&type=image"
        data, content_type = encode_multipart({}, {"media": image_path})
        req = request.Request(url, data=data, headers={"Content-Type": content_type}, method="POST")
        with request.urlopen(req, timeout=30) as response:
            text = response.read().decode("utf-8")
        payload = json.loads(text)
        print("wechat media upload response:", text, flush=True)
        if payload.get("errcode") not in [None, 0] or not payload.get("media_id"):
            raise RuntimeError("upload material failed: " + text)
        return payload

    def send_customer_image(self, access_token, touser, media_id):
        url = "https://api.weixin.qq.com/cgi-bin/message/custom/send?access_token=" + parse.quote(access_token)
        payload = {"touser": touser, "msgtype": "image", "image": {"media_id": media_id}}
        result = http_json("POST", url, payload)
        print("wechat image send response:", json.dumps(result, ensure_ascii=False, separators=(",", ":")), flush=True)
        if result.get("errcode") != 0:
            raise RuntimeError("send message failed: " + json.dumps(result, ensure_ascii=False))
        return result


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
