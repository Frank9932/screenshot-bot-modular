# Workflow Module

## Responsibility
Coordinate capability modules into the WeChat image reply use case. This is the only layer that orchestrates browser capture, desktop capture, latency/error image creation, WeChat image sending, and storing images users send to the bot.

## Public API
- `WeChatImageReplyWorkflow(config_path, image_sender, browser, desktop, virtual_desktop, screenshot_dir, media_downloader, incoming_image_store)`
- `WeChatImageReplyWorkflow.handle(message, received_at, started)`
- `WeChatImageReplyWorkflow.ready_payload()`
- `build_wechat_official_server(config_path, host, port, path)`

## Input
- Parsed WeChat message dictionary
- Config path
- Injected capability module instances
- Environment variables defined by config: webhook token, AppID, AppSecret

## Output
- Workflow result dictionary with screenshot, upload, send, latency, and incoming-image fields
- Configured `WeChatWebhookServer` instance from the builder
- For `image` messages, the user's uploaded photo saved via `incoming_image_store`
  (`{incoming_image_dir}/{FromUserName}/...png`, default `storage/incoming`), independent of
  whether the reply flow captures a screenshot back to them. A download/save failure is recorded
  in `incoming_image_error` and does not block the reply.
- For a `browser_target` capture reply, `message["FromUserName"]` is passed to
  `browser.capture(..., user_id=...)` so that capture's own audit copy (see
  `browser/README.md` → "Team-per-tab targets") is organized by requester, not just by which
  team_id/tab they used. The workflow itself never needs to know tabs exist — it always calls
  `browser.capture(team_id, user_id=...)` and the browser module resolves the tab from that
  team_id's own config.

## Dependencies
- Browser capability API
- Desktop capability API
- Runtime utility API
- WeChat capability API
- Screenshot store capability API
- Shared config helpers

## Run
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Start-WebhookOnly.ps1 -ConfigPath .\config.example.json
```

## Test
```powershell
$env:PYTHONPATH="$PWD\src"
python - <<'PY'
from pathlib import Path
from screenshot_bot.workflow import WeChatImageReplyWorkflow

class MockSender:
    def send_image_file(self, touser, image_path):
        return {'media_id': 'mock-media', 'upload_response': {'ok': True}, 'send_response': {'errcode': 0}}
class MockBrowser:
    class targets:
        enabled = True
        targets = {'1': {}}
    def parse_team_id(self, text): return '1' if text.strip() == '1' else None
    def capture(self, team_id, output_dir=None, image_name=None, timeout_seconds=15):
        p = Path(output_dir) / image_name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b'mock')
        return {'published_path': str(p), 'capture_ms': 1}
class MockDesktop:
    def capture(self, **kwargs): return {'published_path': 'mock.png', 'capture_ms': 1}
class MockVD:
    enabled = False
class MockMediaDownloader:
    def download(self, media_id): return b'mock-image-bytes'
from screenshot_bot.screenshot_store import ScreenshotStore

wf = WeChatImageReplyWorkflow(
    'config.example.json', MockSender(), MockBrowser(), MockDesktop(), MockVD(), 'runtime/mock',
    MockMediaDownloader(), ScreenshotStore(base_dir='runtime/mock-incoming'),
)
print(wf.handle({'MsgType': 'text', 'Content': '1', 'FromUserName': 'user', 'MsgId': '1'}, 'now', 0)['ok'])
PY
```

## Example
```python
from screenshot_bot.workflow import build_wechat_official_server

server = build_wechat_official_server('config.example.json', '127.0.0.1', 8790, '/wechat/official/webhook')
server.serve_forever()
```
