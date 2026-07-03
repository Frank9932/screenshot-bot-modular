# Workflow Module

## Responsibility
Coordinate capability modules into the WeChat image reply use case. This is the only layer that orchestrates browser capture, desktop capture, latency/error image creation, and WeChat image sending.

## Public API
- `WeChatImageReplyWorkflow(config_path, image_sender, browser, desktop, virtual_desktop, screenshot_dir)`
- `WeChatImageReplyWorkflow.handle(message, received_at, started)`
- `WeChatImageReplyWorkflow.ready_payload()`
- `build_wechat_official_server(config_path, host, port, path)`

## Input
- Parsed WeChat message dictionary
- Config path
- Injected capability module instances
- Environment variables defined by config: webhook token, AppID, AppSecret

## Output
- Workflow result dictionary with screenshot, upload, send, and latency fields
- Configured `WeChatWebhookServer` instance from the builder

## Dependencies
- Browser capability API
- Desktop capability API
- Runtime utility API
- WeChat capability API
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

wf = WeChatImageReplyWorkflow('config.example.json', MockSender(), MockBrowser(), MockDesktop(), MockVD(), 'runtime/mock')
print(wf.handle({'MsgType': 'text', 'Content': '1', 'FromUserName': 'user', 'MsgId': '1'}, 'now', 0)['ok'])
PY
```

## Example
```python
from screenshot_bot.workflow import build_wechat_official_server

server = build_wechat_official_server('config.example.json', '127.0.0.1', 8790, '/wechat/official/webhook')
server.serve_forever()
```
