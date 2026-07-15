# Workflow Module

## Responsibility
Coordinate capability modules into the WeChat image reply use case. This is the only layer that orchestrates browser capture, latency/error image creation, WeChat image sending, and storing images users send to the bot. It also dispatches watermark-customization chat commands (`水印`/`watermark`) entirely on its own — a self-contained sub-flow that never reaches the capture dispatch.

## Public API
- `WeChatImageReplyWorkflow(config_path, image_sender, browser, screenshot_dir, media_downloader, incoming_image_store, private_image_store=None)`
- `WeChatImageReplyWorkflow.handle(message, received_at, started)`
- `WeChatImageReplyWorkflow.ready_payload()`
- `build_wechat_official_server(config_path, host, port, path)`
- `watermark_commands.parse_watermark_command(text)` — returns `None` for non-watermark text, or
  a dict describing the parsed action (see "Output" below and root `README.md` → "Watermark
  customization" for the full command grammar)
- `watermark_commands.HELP_TEXT` — the help message sent for `水印`/`水印 帮助`/an unrecognized
  watermark command
- `UserTeamTracker(path)` — persists each WeChat user's currently joined channel (team_id) and
  whether they've unlocked the private channel; workflow owns one instance internally
  (`.user_team_tracker`), see "Channels and photo capture" below
- `help_text.build_general_help_text(visible_channel_ids)` — sent for a bare `帮助`/`help`
  message, listing only the passed-in (non-backup) channel ids
- `help_text.build_channel_guidance(channel_id, visible_channel_ids)` — the default reply for
  anything else unrecognized: pass `UNASSIGNED` (or any falsy value) for a sender with no channel
  yet, or a real channel id to remind a sender what they're already in. Written 傻瓜式
  (plain-language, assumes no technical background) since it may be the first thing a confused
  sender ever reads from the bot
- `help_text.PRIVATE_CHANNEL_PASSCODE` — the exact text (`"11223344"`) that unlocks private-channel
  access for a sender; see "Private channel" below

## Input
- Parsed WeChat message dictionary
- Config path
- Injected capability module instances
- Environment variables defined by config: webhook token, AppID, AppSecret

## Output
- Workflow result dictionary with screenshot, upload, send, latency, and incoming-image fields.
  Every reply (text or image) surfaces `token_ms`/`send_ms` from `image_sender`'s per-call timing,
  and an image reply additionally surfaces `upload_ms` — see `wechat/README.md` for what each
  covers. This is what actually explains a slow `total_latency`: capture/watermark timing alone
  doesn't account for the WeChat API round trips.
- Configured `WeChatWebhookServer` instance from the builder
- For every `image` message, the user's uploaded photo is archived via `incoming_image_store`
  (`{incoming_image_dir}/{user_id}/channel_{team_id}/...png`, default `storage/incoming`, one
  subfolder per sender, channel nested inside it, or `{user_id}/channel_unassigned/...` before
  the sender has joined one) — independent of whether the reply flow also captures a screenshot
  back to them. A download/save failure is recorded in `incoming_image_error` and does not block
  the reply. See "Channels and photo capture" below for how `team_id` is determined and when a
  capture reply is also sent.
- For a `browser_target` capture reply, `message["FromUserName"]` is passed to
  `browser.capture(..., user_id=...)` so that capture's own audit copy (see `browser/README.md`
  → "Team-per-tab targets") is filed under that same `{user_id}/channel_{team_id}` folder — the
  same layout incoming photos use, so everything sent to and received from one sender lives
  together. The workflow itself never needs to know tabs exist — it always calls
  `browser.capture(team_id, user_id=...)` and the browser module resolves the tab from that
  team_id's own config. The output filename is prefixed with the channel (`channel{id}-...`,
  falling back to `wechat-official-...` otherwise) instead of a generic name. If this is the
  sender's first-ever channel join, a follow-up `send_text` call tells them their images are
  archived per-user, and the response carries `first_join_notice_send_response`.
- For a watermark command, no screenshot is taken at all: the result carries `watermark_command`
  (the parsed dict) and `reply_text` (the text sent back), and `image_sender.send_text(touser,
  reply_text)` is called instead of `send_image_file`. See `browser/README.md` → "Per-team
  watermark customization" for what the command actually mutates.
- For a bare `帮助`/`help` message, `reply_text` is `help_text.build_general_help_text(...)` for
  the currently configured non-backup channels, sent via `send_text` — no screenshot involved.
- For any other text that isn't a channel digit, a watermark command, or the private-channel
  passcode, `trigger_kind` is `"guidance"` and `reply_text` is `help_text.build_channel_guidance(...)`
  for the sender's current channel — a text reply instead of a generated placeholder screenshot,
  since a meaningless placeholder doesn't help an actual end user who typed something the bot
  didn't understand.

## Channels and photo capture

A channel (`team_id` internally, any string key configured under `browser_targets.targets`) is
something a WeChat user *joins*, not a one-shot parameter on a single message. Sending a bare
digit both captures that channel's screenshot immediately (unchanged from before) *and* records
it as this sender's currently joined channel, via `UserTeamTracker` — a simple persisted
last-seen lookup (`runtime/user-team-tracker.json` by default,
`wechat_official_webhook.user_team_tracker_path` to override). This is deliberately *not* a
conversation/session state machine — it is one key-value fact (current channel) plus a
private-channel-unlocked flag, with no steps, no timeout, and no per-user flow to get stuck in.

An `image` message (a photo a WeChat user sends *to* the bot) carries no channel digit of its
own, unlike a capture request. `_build_response_image` resolves it from `UserTeamTracker` instead:
if the sender has a joined channel, the photo is treated exactly like a capture request for that
channel (same `browser.capture(...)` call, same reply-with-image flow) — so once a user has
joined once, sending any photo re-captures their channel without needing to resend the digit. If
the sender has never joined a channel, `handle()` returns `help_text.build_channel_guidance(UNASSIGNED, ...)`
as a text reply instead of reaching the capture dispatch at all, and the photo is still archived
either way.

Any other unrecognized text (not a digit, not `水印`, not `帮助`, not the private-channel
passcode) gets the same guidance treatment, tailored to whether that sender already has a
channel — see "Output" above.

Channels marked `"backup": true` in config behave identically to any other channel — they're just
excluded from `browser.targets.visible_targets`, the set passed into the help/guidance text
builders, so they never show up as something to try.

## Private channel

`私密`/`private` (`help_text.PRIVATE_CHANNEL_WORDS`) is inert by default: sending it falls through
to the same guidance reply as any other unrecognized text. It only does something once a sender
has first sent the exact passcode `help_text.PRIVATE_CHANNEL_PASSCODE` (`"11223344"`), which calls
`UserTeamTracker.unlock_private(touser)` and replies with `help_text.PRIVATE_CHANNEL_UNLOCKED_TEXT`.
After that, `私密`/`private` joins a special channel (`user_team_tracker.PRIVATE_CHANNEL_ID`) that
is not backed by any `browser_targets` entry — it exists purely to archive whatever a sender
uploads. Sending it replies with `help_text.PRIVATE_CHANNEL_JOINED_TEXT`, and every subsequent
photo from that sender is saved via `private_image_store` (config:
`wechat_official_webhook.private_channel.save_dir`, default `storage/private`) under that
sender's own `{user_id}` subfolder — one folder per sender rather than one shared flat folder.
`handle()` replies with `help_text.PRIVATE_CHANNEL_SAVED_TEXT` and returns immediately — unlike
regular channels, it never reaches `_build_response_image`/`browser.capture`, since there is no
target to capture from. To leave the private channel, the sender just sends any channel digit.

## Dependencies
- Browser capability API
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
        return {'media_id': 'mock-media', 'upload_response': {'ok': True}, 'send_response': {'errcode': 0}, 'token_ms': 1, 'upload_ms': 1, 'send_ms': 1}
    def send_text(self, touser, content):
        print('text reply:', content)
        return {'send_response': {'errcode': 0}, 'token_ms': 1, 'send_ms': 1}
class MockBrowser:
    class targets:
        enabled = True
        targets = {'1': {}}
        visible_targets = {'1': {}}
    def parse_team_id(self, text): return '1' if text.strip() == '1' else None
    def capture(self, team_id, output_dir=None, image_name=None, user_id=None, timeout_seconds=15):
        p = Path(output_dir) / image_name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b'mock')
        return {'published_path': str(p), 'capture_ms': 1}
    def describe_watermark(self, team_id):
        return {'team_id': team_id, 'fields': [], 'background_opacity': 100, 'customized': False}
class MockMediaDownloader:
    def download(self, media_id): return b'mock-image-bytes'
from screenshot_bot.screenshot_store import ScreenshotStore

wf = WeChatImageReplyWorkflow(
    'config.example.json', MockSender(), MockBrowser(), 'runtime/mock',
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
