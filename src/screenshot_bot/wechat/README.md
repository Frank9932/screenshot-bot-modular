# WeChat Capability Module

## Responsibility
Handle WeChat Official Account protocol and API calls. It does not decide which screenshot to create.

## Public API
- `WeChatWebhookServer(address, webhook_path, token, message_processor, ready_payload=None, log_path=None, dedupe_ttl_seconds=600)`
- `WeChatOfficialClient(appid, appsecret)`
- `WeChatImageSender(appid, appsecret, client=None)` — `send_image_file(touser, image_path)` and
  `send_text(touser, content)`, both retrying once on an expired/invalid access token. Each
  returns per-call timing alongside the response: `send_image_file` returns `token_ms`,
  `upload_ms`, `send_ms` (access-token fetch, media upload, message send, timed individually);
  `send_text` returns `token_ms`, `send_ms`. This is the only place these three WeChat API round
  trips are measured — `capture_ms`/`watermark_ms` only cover the browser side, so a slow reply
  that isn't a slow capture has to show up in one of these instead.
- `WeChatOfficialClient.send_customer_text(access_token, touser, content)`
- `WeChatOfficialClient.create_menu(access_token, menu) -> dict` — `cgi-bin/menu/create`
- `WeChatOfficialClient.get_menu(access_token) -> dict` — `cgi-bin/menu/get`
- `WeChatMenuManager(appid, appsecret, client=None)` — `set_menu(menu)` and `get_menu()`, same
  retry-once-on-invalid-token pattern as `WeChatImageSender`. The menu payload itself (which
  buttons, which `EventKey`s) is built by `screenshot_bot.workflow.menu`, not here — this class
  only pushes/reads whatever payload it's given.
- `WeChatMediaDownloader(appid=None, appsecret=None, client=None)`
- `WeChatMediaDownloader.download(media_id) -> bytes`
- `verify_wechat_signature(token, query)` — a failed check on either `do_GET`/`do_POST` logs the
  rejection (console `log_line("webhook", ...)`, and for POST also a JSONL event
  `{"ok": false, "error": "invalid signature", ...}`) before returning 403. Previously silent:
  a token/URL mismatch between this host's config and what's registered in the WeChat console
  produced zero trace in any log this project ships, making it indistinguishable from a dead
  tunnel or a crashed process from every other signal (health check, browser state, uptime).
- `parse_xml_message(body)`
- `message_dedupe_key(message)`

## Input
- WeChat GET verification query
- WeChat POST XML body
- `message_processor` object exposing `handle(message, received_at, started)`
- AppID/AppSecret and target user id for image sending
- `MediaId` from an incoming image message for downloading

## Output
- HTTP `success` ACK for WeChat POSTs
- Parsed message dictionaries
- WeChat media upload, image send, text send, and media download (`cgi-bin/media/get`) API responses
- JSONL event records through injected log path

## Dependencies
- WeChat Official Account test account or service account API credentials
- Python standard HTTP server and urllib
- Runtime utilities for dedupe and logging

## Run
The webhook server is started by a workflow or script that injects a message processor.

## Test
```powershell
$env:PYTHONPATH="$PWD\src"
python - <<'PY'
from screenshot_bot.wechat.xml_message import parse_xml_message
body = b'<xml><MsgType><![CDATA[text]]></MsgType><Content><![CDATA[1]]></Content><FromUserName><![CDATA[user]]></FromUserName><MsgId>42</MsgId></xml>'
print(parse_xml_message(body))
PY
```

## Example
```python
from screenshot_bot.wechat.webhook_server import WeChatWebhookServer

class MockProcessor:
    def handle(self, message, received_at, started):
        return {'ok': True, 'content': message.get('Content', '')}

server = WeChatWebhookServer(('127.0.0.1', 8790), '/wechat/official/webhook', 'token', MockProcessor())
```
