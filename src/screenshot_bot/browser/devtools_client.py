import base64
import json
import os
import socket
import struct
from urllib.parse import quote, urlparse
from urllib.request import urlopen


def http_json(url, timeout=5):
    with urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def find_page(port, target_config):
    pages = http_json(f"http://127.0.0.1:{port}/json/list")
    candidates = [page for page in pages if page.get("type") == "page" and page.get("webSocketDebuggerUrl")]
    capture_candidates = [page for page in candidates if not _is_identity_page(page, target_config)]
    match_url = str(target_config.get("match_url", "") or "")
    match_title = str(target_config.get("match_title", "") or "")
    search_pages = capture_candidates if capture_candidates else candidates
    if match_url:
        for page in search_pages:
            if match_url in str(page.get("url", "")):
                return page
    if match_title:
        for page in search_pages:
            if match_title in str(page.get("title", "")):
                return page
    if capture_candidates:
        return capture_candidates[0]
    if candidates:
        return candidates[0]

    start_url = str(target_config.get("start_url", "about:blank") or "about:blank")
    http_json(f"http://127.0.0.1:{port}/json/new?{quote(start_url, safe=':/?&=%#')}")
    pages = http_json(f"http://127.0.0.1:{port}/json/list")
    for page in pages:
        if page.get("type") == "page" and page.get("webSocketDebuggerUrl"):
            return page
    raise RuntimeError(f"no debuggable page found on port {port}")


def capture_page_png(websocket_url, timeout_seconds=15):
    with DevToolsWebSocket(websocket_url, timeout=timeout_seconds) as client:
        client.call("Page.enable")
        client.call("Page.bringToFront")
        result = client.call("Page.captureScreenshot", {"format": "png", "fromSurface": True})
    return base64.b64decode(result["data"])


def _is_identity_page(page, target_config):
    title = str(page.get("title", ""))
    url = str(page.get("url", ""))
    identity_title = str(target_config.get("identity_title", "") or "")
    identity_url = str(target_config.get("identity_url", "") or "")
    start_url = str(target_config.get("start_url", "") or "")
    if identity_title and identity_title in title:
        return True
    if identity_url and identity_url in url:
        return True
    if start_url and start_url == url and "browser-target-pages" in url:
        return True
    return False


class DevToolsWebSocket:
    def __init__(self, websocket_url, timeout=10):
        parsed = urlparse(websocket_url)
        if parsed.scheme != "ws":
            raise ValueError(f"unsupported websocket scheme: {parsed.scheme}")
        self.host = parsed.hostname
        self.port = parsed.port or 80
        self.path = parsed.path + (("?" + parsed.query) if parsed.query else "")
        self.timeout = timeout
        self.sock = None
        self.next_id = 1

    def __enter__(self):
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(request.encode("ascii"))
        response = self.sock.recv(4096)
        if b" 101 " not in response.split(b"\r\n", 1)[0]:
            raise RuntimeError(f"websocket upgrade failed: {response[:200]!r}")
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.sock:
            self.sock.close()

    def call(self, method, params=None):
        message_id = self.next_id
        self.next_id += 1
        self._send_text(json.dumps({"id": message_id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(self._recv_text())
            if message.get("id") != message_id:
                continue
            if "error" in message:
                raise RuntimeError(f"CDP {method} failed: {message['error']}")
            return message.get("result") or {}

    def _send_text(self, payload):
        data = payload.encode("utf-8")
        header = bytearray([0x81])
        length = len(data)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        mask = os.urandom(4)
        header.extend(mask)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(data))
        self.sock.sendall(bytes(header) + masked)

    def _recv_text(self):
        first = self.sock.recv(2)
        if len(first) < 2:
            raise RuntimeError("websocket closed")
        opcode = first[0] & 0x0F
        length = first[1] & 0x7F
        masked = bool(first[1] & 0x80)
        if length == 126:
            length = struct.unpack("!H", self.sock.recv(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self.sock.recv(8))[0]
        mask = self.sock.recv(4) if masked else b""
        data = self._recv_exact(length)
        if masked:
            data = bytes(byte ^ mask[index % 4] for index, byte in enumerate(data))
        if opcode == 0x8:
            raise RuntimeError("websocket closed by peer")
        if opcode == 0x9:
            return self._recv_text()
        return data.decode("utf-8")

    def _recv_exact(self, length):
        chunks = []
        remaining = length
        while remaining:
            chunk = self.sock.recv(remaining)
            if not chunk:
                raise RuntimeError("websocket closed during frame")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
