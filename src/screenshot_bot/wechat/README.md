# WeChat Capability Module

## Responsibility
Handle WeChat Official Account protocol and API calls. It does not decide which screenshot to create.

## Public API
- `WeChatWebhookServer(address, webhook_path, token, message_processor, ready_payload=None, log_path=None, dedupe_ttl_seconds=600)`
- `WeChatOfficialClient(appid, appsecret)`
- `WeChatImageSender(appid, appsecret, client=None)` — `send_image_file(touser, image_path)` and
  `send_text(touser, content)`, both retrying once on an expired/invalid access token
- `WeChatOfficialClient.send_customer_text(access_token, touser, content)`
- `WeChatMediaDownloader(appid=None, appsecret=None, client=None)`
- `WeChatMediaDownloader.download(media_id) -> bytes`
- `verify_wechat_signature(token, query)`
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
