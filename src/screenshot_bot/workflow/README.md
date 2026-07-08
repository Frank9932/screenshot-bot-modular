# Workflow Module

## Responsibility
Coordinate capability modules into the WeChat image reply use case. This is the only layer that orchestrates browser capture, desktop capture, latency/error image creation, WeChat image sending, and storing images users send to the bot. It also dispatches watermark-customization chat commands (`水印`/`watermark`) entirely on its own — a self-contained sub-flow that never reaches the capture dispatch.

## Public API
- `WeChatImageReplyWorkflow(config_path, image_sender, browser, desktop, virtual_desktop, screenshot_dir, media_downloader, incoming_image_store)`
- `WeChatImageReplyWorkflow.handle(message, received_at, started)`
- `WeChatImageReplyWorkflow.ready_payload()`
- `build_wechat_official_server(config_path, host, port, path)`
- `watermark_commands.parse_watermark_command(text)` — returns `None` for non-watermark text, or
  a dict describing the parsed action (see "Output" below and root `README.md` → "Watermark
  customization" for the full command grammar)
- `watermark_commands.HELP_TEXT` — the help message sent for `水印`/`水印 帮助`/an unrecognized
  watermark command
- `UserTeamTracker(path)` — persists each WeChat user's currently joined channel (team_id);
  workflow owns one instance internally (`.user_team_tracker`), see "Channels and photo capture"
  below
- `help_text.GENERAL_HELP_TEXT` — sent for a bare `帮助`/`help` message
- `help_text.CHANNEL_UNASSIGNED_PROMPT` — sent when a photo arrives from a sender who hasn't
  joined a channel yet

## Input
- Parsed WeChat message dictionary
- Config path
- Injected capability module instances
- Environment variables defined by config: webhook token, AppID, AppSecret

## Output
- Workflow result dictionary with screenshot, upload, send, latency, and incoming-image fields
- Configured `WeChatWebhookServer` instance from the builder
- For every `image` message, the user's uploaded photo is archived via `incoming_image_store`
  (`{incoming_image_dir}/channel_{team_id}/...png`, default `storage/incoming`, one flat folder
  per channel, or `channel_unassigned/...` before the sender has joined one) — independent of
  whether the reply flow also captures a screenshot back to them. A download/save failure is
  recorded in `incoming_image_error` and does not block the reply. See "Channels and photo
  capture" below for how `team_id` is determined and when a capture reply is also sent.
- For a `browser_target` capture reply, `message["FromUserName"]` is passed to
  `browser.capture(..., user_id=...)` so that capture's own audit copy (see `browser/README.md`
  → "Team-per-tab targets") is filed under that channel's folder. The workflow itself never needs
  to know tabs exist — it always calls `browser.capture(team_id, user_id=...)` and the browser
  module resolves the tab from that team_id's own config. The output filename is prefixed with
  the channel (`channel{id}-...`, or `desktop{n}-...` for a virtual-desktop capture, falling back
  to `wechat-official-...` otherwise) instead of a generic name.
- For a watermark command, no screenshot is taken at all: the result carries `watermark_command`
  (the parsed dict) and `reply_text` (the text sent back), and `image_sender.send_text(touser,
  reply_text)` is called instead of `send_image_file`. See `browser/README.md` → "Per-team
  watermark customization" for what the command actually mutates.
- For a bare `帮助`/`help` message, `reply_text` is `help_text.GENERAL_HELP_TEXT`, sent via
  `send_text` — no screenshot involved.

## Channels and photo capture

A channel (`team_id` internally, `1`-`5`) is something a WeChat user *joins*, not a one-shot
parameter on a single message. Sending a bare digit both captures that channel's screenshot
immediately (unchanged from before) *and* records it as this sender's currently joined channel,
via `UserTeamTracker` — a simple persisted last-seen lookup (`runtime/user-team-tracker.json` by
default, `wechat_official_webhook.user_team_tracker_path` to override). This is deliberately
*not* a conversation/session state machine — it is one key-value fact (current channel) with no
steps, no timeout, and no per-user flow to get stuck in.

An `image` message (a photo a WeChat user sends *to* the bot) carries no channel digit of its
own, unlike a capture request. `_build_response_image` resolves it from `UserTeamTracker` instead:
if the sender has a joined channel, the photo is treated exactly like a capture request for that
channel (same `browser.capture(...)` call, same reply-with-image flow) — so once a user has
joined once, sending any photo re-captures their channel without needing to resend the digit. If
the sender has never joined a channel, `handle()` returns `help_text.CHANNEL_UNASSIGNED_PROMPT`
as a text reply instead of reaching the capture dispatch at all, and the photo is still archived
either way.

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
    def send_text(self, touser, content):
        print('text reply:', content)
        return {'send_response': {'errcode': 0}}
class MockBrowser:
    class targets:
        enabled = True
        targets = {'1': {}}
    def parse_team_id(self, text): return '1' if text.strip() == '1' else None
    def capture(self, team_id, output_dir=None, image_name=None, user_id=None, timeout_seconds=15):
        p = Path(output_dir) / image_name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b'mock')
        return {'published_path': str(p), 'capture_ms': 1}
    def describe_watermark(self, team_id):
        return {'team_id': team_id, 'fields': [], 'background_opacity': 100, 'customized': False}
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
print(wf.handle({'MsgType': 'text', 'Content': u'帮助', 'FromUserName': 'user', 'MsgId': '0'}, 'now', 0)['ok'])
# join channel 1 -- captures immediately AND records "user" as now in channel 1
print(wf.handle({'MsgType': 'text', 'Content': '1', 'FromUserName': 'user', 'MsgId': '1'}, 'now', 0)['ok'])
# a photo from "user" now re-captures channel 1 without resending the digit
print(wf.handle({'MsgType': 'image', 'MediaId': 'm1', 'FromUserName': 'user', 'MsgId': '2'}, 'now', 0)['ok'])
print(wf.handle({'MsgType': 'text', 'Content': u'水印 1 状态', 'FromUserName': 'user', 'MsgId': '3'}, 'now', 0)['ok'])
PY
```

## Example
```python
from screenshot_bot.workflow import build_wechat_official_server

server = build_wechat_official_server('config.example.json', '127.0.0.1', 8790, '/wechat/official/webhook')
server.serve_forever()
```
