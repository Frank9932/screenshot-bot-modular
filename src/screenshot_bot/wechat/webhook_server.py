import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import parse

from screenshot_bot.runtime.clock import utc_now_iso
from screenshot_bot.runtime.console_log import log_line
from screenshot_bot.runtime.dedupe import MessageDedupe
from screenshot_bot.runtime.jsonl import JsonlLogger
from screenshot_bot.wechat.signature import verify_wechat_signature
from screenshot_bot.wechat.xml_message import message_dedupe_key, parse_xml_message


class WeChatWebhookServer(ThreadingHTTPServer):
    # http.server.HTTPServer sets allow_reuse_address = 1. On Windows this doesn't just permit
    # rebinding a socket stuck in TIME_WAIT (the POSIX use case) -- it lets a second process bind
    # the exact same port while a prior instance is still actively listening, with no error at
    # all. That silent coexistence is what let every uncoordinated restart (a manual console run,
    # a stray scheduled task, an ansible retry) leave an orphan process alive undetected, each
    # with its own independent Chrome tab bookkeeping racing the other -- the actual root cause
    # behind repeated "tab not debuggable" incidents. Disabling reuse makes a port collision fail
    # loudly at startup instead of silently producing a split-brain.
    allow_reuse_address = False

    def __init__(self, address, webhook_path, token, message_processor, ready_payload=None, log_path=None, dedupe_ttl_seconds=600):
        super().__init__(address, WeChatWebhookHandler)
        self.webhook_path = webhook_path
        self.token = token
        self.logger = JsonlLogger(log_path)
        self.dedupe = MessageDedupe(dedupe_ttl_seconds)
        self.message_processor = message_processor
        self.ready_payload = {
            "ok": True,
            "host": address[0],
            "port": address[1],
            "path": webhook_path,
            "dedupe_ttl_seconds": self.dedupe.ttl_seconds,
            "time": utc_now_iso(),
            **(ready_payload or {}),
        }


class WeChatWebhookHandler(BaseHTTPRequestHandler):
    server_version = "WeChatOfficialWebhook/2.0"

    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self._json(200, {"ok": True, "time": utc_now_iso(), "webhook_path": self.server.webhook_path})
            return
        if path != self.server.webhook_path:
            self._json(404, {"ok": False, "error": "unknown path"})
            return
        query = parse.parse_qs(parse.urlsplit(self.path).query)
        if not verify_wechat_signature(self.server.token, query):
            # A silent 403 here (the previous behavior) is indistinguishable from "no request
            # ever arrived at all" -- neither the console log nor the JSONL event log carried any
            # trace of it, which made a token/URL mismatch between this host's config and what's
            # registered in the WeChat console look identical to a dead tunnel or a crashed
            # process from every other signal (health check, browser state, uptime).
            log_line("webhook", f"GET signature verification failed from {self.client_address[0]}")
            self._text(403, "invalid signature")
            return
        self._text(200, query.get("echostr", [""])[0])

    def do_POST(self):
        received_at = utc_now_iso()
        started = time.perf_counter()
        if self.path.split("?", 1)[0] != self.server.webhook_path:
            self._json(404, {"ok": False, "error": "unknown path"})
            return
        query = parse.parse_qs(parse.urlsplit(self.path).query)
        if not verify_wechat_signature(self.server.token, query):
            # Same visibility gap as do_GET above, but this is the one that actually matters
            # operationally: every real WeChat message comes in as a POST, so a token/URL
            # mismatch here means every message a user sends vanishes without a single line in
            # any log this project ships -- logging it to both the console (quick glance while
            # tailing server.out.log) and the JSONL (so it shows up next to real message events,
            # not just something you'd catch by chance) closes that gap.
            log_line("webhook", f"POST signature verification failed from {self.client_address[0]}")
            self.server.logger.write(
                {"received_at": received_at, "ok": False, "error": "invalid signature", "remote_addr": self.client_address[0]}
            )
            self._text(403, "invalid signature")
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        try:
            message = parse_xml_message(body)
            key = message_dedupe_key(message)
            if not self.server.dedupe.mark_first_seen(key):
                self.server.logger.write(
                    {
                        "received_at": received_at,
                        "msg_type": message.get("MsgType", ""),
                        "touser": message.get("FromUserName", ""),
                        "content": message.get("Content", ""),
                        "msg_id": message.get("MsgId", ""),
                        "dedupe_key": key,
                        "ignored": True,
                        "reason": "duplicate message",
                        "ack_latency": round((time.perf_counter() - started) * 1000.0, 1),
                        "ok": True,
                    }
                )
                self._text(200, "success")
                return
            threading.Thread(target=self._process_async, args=(message, received_at, started, key), daemon=True).start()
        except Exception as exc:
            self.server.logger.write({"received_at": received_at, "error": str(exc), "ok": False})
        self._text(200, "success")

    def _process_async(self, message, received_at, started, key):
        try:
            result = self.server.message_processor.handle(message, received_at, started)
            result["dedupe_key"] = key
            self.server.logger.write(result)
        except Exception as exc:
            self.server.logger.write(
                {
                    "received_at": received_at,
                    "msg_type": message.get("MsgType", ""),
                    "touser": message.get("FromUserName", ""),
                    "content": message.get("Content", ""),
                    "msg_id": message.get("MsgId", ""),
                    "dedupe_key": key,
                    "error": str(exc),
                    "ok": False,
                }
            )

    def _text(self, status, text):
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
