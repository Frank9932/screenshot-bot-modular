# Workflow Module

## Responsibility
Coordinate capability modules into the WeChat image reply use case. This is the only layer that orchestrates browser capture, latency/error image creation, WeChat image sending, and storing images users send to the bot. It also dispatches watermark-customization chat commands (`水印`/`watermark`) entirely on its own — a self-contained sub-flow that never reaches the capture dispatch.

Split into two layers on purpose (see "Message routing" below): `message_router.route_message`
decides *what* should happen given a message and the sender's state, as a pure function with no
I/O; `WeChatImageReplyWorkflow` is the thin layer that executes that decision (sends replies,
captures screenshots, persists state). The decision logic can be tested/debugged completely on
its own — no WeChat API, no browser, no config file.

## Public API
- `WeChatImageReplyWorkflow(config_path, image_sender, browser, screenshot_dir, media_downloader, incoming_image_store, private_image_store=None)`
- `WeChatImageReplyWorkflow.handle(message, received_at, started)`
- `WeChatImageReplyWorkflow.ready_payload()`
- `build_wechat_official_server(config_path, host, port, path)`
- `message_router.route_message(msg_type, content, channel_id, private_unlocked, all_channel_ids, ignore_message_types, equipment_catalog_enabled=False, equipment_stage=None, equipment_categories=None, equipment_items=None)`
  — pure decision function, see "Message routing" below and "Select-equipment flow" for the
  `equipment_*` parameters
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
- `menu.build_menu_payload(visible_channel_ids, equipment_enabled=False)` — the WeChat
  `menu/create` request body: `选择频道` submenu (max 5 channels) + `帮助` + `水印帮助` by default,
  or `选择设备` + `选择频道` + `获取截图` when `equipment_enabled` (see "Tap menu" and
  "Select-equipment flow" below)
- `menu.event_key_to_text(event_key)` — translates a menu tap's `EventKey` back into the plain
  text typing the equivalent command would send, or `None` for an unrecognized/stale key
- `equipment_catalog.load_categories(csv_path)` / `.load_equipment(csv_path, category)` — read
  the equipment CSV (columns: `category`, `equipment`, `path`); see "Select-equipment flow" below
- `equipment_selection_tracker.EquipmentSelectionTracker(path)` — persists each sender's
  in-progress/confirmed equipment selection; workflow owns one instance internally
  (`.equipment_selection_tracker`)
- `equipment_prompts` — trigger words (`EQUIPMENT_START_WORDS`, etc.) and reply-text builders for
  the select-equipment flow, mirroring `help_text.py`'s role for the simpler channel flow

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

## Message routing (debuggable in isolation)

`message_router.py` holds every "what should happen next" decision as one pure function,
`route_message(msg_type, content, channel_id, private_unlocked, all_channel_ids, ignore_message_types, equipment_catalog_enabled=False, equipment_stage=None, equipment_categories=None, equipment_items=None)`
— given the message plus the sender's already-looked-up state, it returns a dict like
`{"kind": "join_channel", "channel_id": "1", "is_first_join": True}` and touches nothing else: no
WeChat API, no browser, no filesystem, no config. `WeChatImageReplyWorkflow.handle()` looks up the
sender's state via `UserTeamTracker`, calls `route_message`, then executes whatever `kind` comes
back (`_reply_text` for anything that's just a text reply, `_capture_and_reply` for
`join_channel`/`recapture`, or the watermark/private-channel-specific handlers).

This split means the entire human-interaction/command-parsing layer can be exercised without
running the bot at all. Run it directly for an interactive REPL:
```powershell
$env:PYTHONPATH="$PWD\src"
python -m screenshot_bot.workflow.message_router
```
Type messages and watch the returned decision; `:image` queues the next input as an image
message, `:channels 1,2,3` changes the configured channel set, `:ignore image` changes which
types are silently dropped, `:equipment_enabled on` turns on the equipment-flow checks (off by
default, matching config), `:equipment_categories A,B,C` / `:equipment_items name:path,...` seed
the category/equipment lists the way the workflow layer would load them from the CSV. The REPL
keeps sender state (channel, private-unlock, equipment stage) in memory across the session, so
you can walk through a full conversation (send the passcode, then `私密`, then a channel digit;
or `:equipment_enabled on` then `设备` → a category digit → an equipment digit → `确认`) and see
exactly which decision fires at each step.

## Tap menu

`menu.py` builds the WeChat custom tap-menu and is the single source of truth for the
button<->`EventKey` scheme, since building the menu (`build_menu_payload`) and interpreting a tap
(`event_key_to_text`) have to agree with each other. `WeChatImageReplyWorkflow.handle()` detects
an incoming `event`/`CLICK` message, translates its `EventKey` via `event_key_to_text`, and — if
recognized — overwrites the *local* `routed_msg_type`/`routed_content` it hands to
`route_message` with `("text", <the equivalent command text>)`, while `result["msg_type"]`/
`result["content"]` in the JSONL log still record the raw event as WeChat actually sent it (plus
`result["menu_event_key"]`). `route_message` itself is completely unaware menu taps exist — a tap
on the "频道1" button and typing `1` produce the identical decision, so there is no separate
tap-handling code path to keep in sync with the typed one. An unrecognized `EventKey` (e.g. left
over from a previously pushed menu) or any non-`CLICK` event (e.g. `subscribe`) falls through
unchanged and is handled exactly as before this feature existed (typically default guidance text).

WeChat allows at most 3 top-level buttons, which `build_menu_payload` spends differently
depending on `equipment_enabled`: `选择频道` (channel submenu) + `帮助` + `水印帮助` when the
equipment catalog isn't configured; `选择设备` + `选择频道` + `获取截图` when it is (see
"Select-equipment flow" below) — `帮助`/`水印` still work fine typed directly in that layout,
they just aren't buttons, since there's no room left in the 3-button budget.

The menu itself is not pushed automatically on startup — it rarely changes (only when the visible
channel set or `equipment_catalog.enabled` changes) and pushing it is an explicit operator action:
```powershell
scripts\Bot.ps1 menu set    # push scripts/run_wechat_menu_sync.py's build from config.json
scripts\Bot.ps1 menu get    # show what's currently live, for verification
```
Both go through `wechat.menu_manager.WeChatMenuManager`, which mirrors `WeChatImageSender`'s
retry-once-on-invalid-token pattern against the same `WeChatOfficialClient.create_menu`/`get_menu`
(`cgi-bin/menu/create`/`cgi-bin/menu/get`).

## Select-equipment flow

An alternative to channel capture for deployments with a large, browsable equipment list (e.g.
many HVAC units under a handful of categories) rather than a handful of fixed channels. Gated
entirely behind `equipment_catalog.enabled` in config (default `false`) — every trigger word
below (`设备`/`获取截图`/`确认`/`取消`) is completely inert when disabled and falls through to
ordinary guidance, same as `PRIVATE_CHANNEL_WORDS` staying inert until unlocked (see
`route_message`'s `equipment_catalog_enabled` parameter).

The flow, driven entirely by `EquipmentSelectionTracker`-persisted per-sender stage (so it
survives a webhook restart) and small builder functions in `equipment_prompts.py`:

1. **`设备`/`equipment`** (typed, or the `选择设备` menu button) — (re)starts the flow at any
   point, overwriting any prior in-progress selection. `equipment_catalog.load_categories(csv_path)`
   loads category names (first-seen CSV order) and the tracker moves to `"awaiting_category"`.
2. A **digit** while `"awaiting_category"` picks that category by 1-based index into the list
   just sent (out of range → `equipment_invalid_selection`, resends the same list with an error
   prefix). The tracker moves to `"awaiting_equipment"`, storing the chosen category, and
   `equipment_catalog.load_equipment(csv_path, category)` lists that category's equipment.
3. A **digit** while `"awaiting_equipment"` picks that equipment the same way. The tracker moves
   to `"awaiting_confirm"`, storing `{category, equipment, path}` (`path` is that CSV row's
   hash-route value, used in step 5).
4. **`确认`/`确认取消`** — `确认` moves the tracker to `"confirmed"` (locking in the selection);
   `取消` resets it to `"none"`. Both only mean anything while `"awaiting_confirm"`; outside that
   stage they're just ordinary unrecognized text.
5. **`获取截图`/`截图`** (typed, or the `获取截图` menu button) — requires both a `"confirmed"`
   selection *and* a joined channel (equipment capture reuses that channel's own tab, so there
   has to be one to reuse; `equipment_capture_no_channel` if not, `equipment_capture_not_ready`
   if no selection is confirmed yet). When both are satisfied,
   `WeChatImageReplyWorkflow._capture_equipment_and_reply` calls
   `browser.capture(channel_id, ..., equipment_path=path, equipment_pane_height=..., equipment_settle_seconds=...)`
   — this reroutes that channel's tab to the equipment's graphic via
   `CdpMultiTabService.navigate_equipment` (see `browser/README.md` → "Equipment navigation")
   *before* screenshotting it, so the reply is that equipment's own graphic, not whatever the
   channel tab happened to be showing before. The output filename is prefixed
   `channel{id}-equipment-{safe_name}-...` and the result carries `equipment_category`/
   `equipment_name` for the JSONL log.

Digit precedence while a category/equipment pick is pending: **every** digit means "list index"
(valid or not) rather than falling through to a channel-join, so a sender mid-flow who mistypes
an index gets told to try again instead of silently switching channels. Once past that stage
(`"awaiting_confirm"`/`"confirmed"`), digits go back to meaning channel selection as normal — a
sender can switch channels after confirming an equipment and before tapping `获取截图`, and the
capture goes to whichever channel is current at that point, not whichever was current when the
equipment was picked.

Config (`equipment_catalog` section): `enabled` (default `false`), `csv_path` (default
`runtime/cdp-explore-out/hvac_equipment.csv` — the same file
`scripts/screenshot_equipment_list.py` reads for offline batch capture), `pane_height` (default
`"12%"`), `settle_seconds` (default `3.0`), `selection_tracker_path` (default
`runtime/equipment-selection-tracker.json`). A missing/unreadable CSV is treated the same as an
empty catalog (`EQUIPMENT_LIST_EMPTY_TEXT`), not a hard error.

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
own, unlike a capture request. `route_message` resolves it from the sender's already-looked-up
channel instead: if they have a joined channel, it returns `{"kind": "recapture", ...}`, executed
identically to a capture request for that channel (same `browser.capture(...)` call, same
reply-with-image flow) — so once a user has joined once, sending any photo re-captures their
channel without needing to resend the digit. If the sender has never joined a channel, the
decision is `unassigned_photo_prompt`, executed as `help_text.build_channel_guidance(UNASSIGNED, ...)`
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
`UserTeamTracker.unlock_private(touser)` and replies with `help_text.PRIVATE_CHANNEL_UNLOCKED_TEXT`
(just a confirmation — it deliberately does not restate the trigger words, so nothing about how
to actually enter is leaked to anyone reading over a sender's shoulder). After that, `私密`/`private`
joins a special channel (`user_team_tracker.PRIVATE_CHANNEL_ID`) that is not backed by any
`browser_targets` entry — it exists purely to archive whatever a sender uploads. Sending it
replies with `help_text.PRIVATE_CHANNEL_JOINED_TEXT`, and every subsequent photo from that sender
is saved via `private_image_store` (config: `wechat_official_webhook.private_channel.save_dir`,
default `storage/private`) under that sender's own `{user_id}` subfolder — one folder per sender
rather than one shared flat folder. `handle()` replies with `help_text.PRIVATE_CHANNEL_SAVED_TEXT`
and returns immediately — unlike regular channels, it never reaches `browser.capture`, since there
is no target to capture from. To leave the private channel, the sender just sends any channel digit.

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
