# Screenshot Bot Modular

Modular WeChat Official Account webhook flow with LINE-compatible routing behavior, refactored
out of [screenshot-bot](https://github.com/Frank9932/screenshot-bot) into capability modules.

This repo intentionally excludes:

- wx-cli
- desktop WeChat polling
- UI-driven WeChat sending
- managing a *production* Cloudflare tunnel

For production, the tunnel stays external — this repo only runs the local HTTP server behind
whatever tunnel is already forwarding to it (see `ansible/README.md` for the deployed default
port). Two tunnel options are provided as convenience tooling, not managed production
infrastructure: `scripts/Start-PublicTunnel.ps1`/`Stop-PublicTunnel.ps1` for a throwaway
Cloudflare quick tunnel (random URL, dies with the process — see "Local Run" below), and
`scripts/Bot.ps1 tunnel permanent-install -TunnelToken <token>` for a permanent named-tunnel
Windows service (stable hostname, survives reboots — see `ansible/README.md` → "Permanent
tunnel").

## Deployment

See [ansible/README.md](ansible/README.md) for WinRM-based Windows 11 deployment. It reuses the
`screenshot-bot` project's Ansible inventory (same lab hosts) and WeChat Official Account secrets.

## Layout

```text
src/screenshot_bot/
  browser/
    target_config.py         input number -> browser target
    cdp_multi_tab_service.py shared Chrome process + named-tab CDP client
    profile_manager.py       shared Chrome process lifecycle, team_id -> tab
    devtools_client.py       low-level CDP websocket/http primitives
    watermark.py             PNG watermark rendering
    watermark_settings.py    per-team watermark overrides (chat-customizable)
    screenshot_service.py    browser screenshot use case
  wechat/
    signature.py           WeChat signature verification
    xml_message.py         XML parsing and message keys
    official_api.py        access_token, media upload/download, image send
    image_sender.py        stable image-send API for workflows
    media_downloader.py    stable incoming-media-download API for workflows
    webhook_server.py      HTTP webhook server, ACK, dedupe, async work
  workflow/
    wechat_image_reply.py  dispatcher: message -> screenshot/latency image -> WeChat image reply
    watermark_commands.py  parses "水印 <team> ..." chat commands (see "Behavior" below)
  runtime/
    clock.py
    dedupe.py
    jsonl.py
    latency_image.py
  screenshot_store/
    store.py               save screenshot bytes -> per-tab dir -> ScreenshotRecord
    models.py               ScreenshotRecord
```


## Behavior

The WeChat webhook mirrors the LINE webhook routing model, built around a channel concept:

- a bare `帮助`/`help` shows a general onboarding message — see "Channels" below.
- text starting with `水印`/`watermark` is a watermark-customization command, not a capture
  trigger — see "Watermark customization" below. Every other rule below only applies to text
  that isn't a watermark command.
- a digit matching any configured channel id **joins that channel and immediately captures its
  screenshot** — several channel numbers may share one physical multi-tab site, each pinned to
  its own tab (see `src/screenshot_bot/browser/README.md` → "Team-per-tab targets"); the output
  filename is prefixed `channel{id}-...`, and both the watermarked and original (pre-watermark)
  bytes are archived per sender, under `{user_id}/channel_{id}/watermarked/...` and
  `{user_id}/channel_{id}/original/...` respectively. The first time a sender ever joins a
  channel, a follow-up text tells them their images are archived under a folder named by their
  own user ID.
- once a sender has joined a channel this way, **sending a photo captures and returns that
  channel's screenshot again** — no need to resend the digit each time. A photo from someone who
  has never joined a channel gets a text prompt telling them to send a digit first, instead of
  being silently ignored. See "Channels" below.
- some channels can be configured as backup/spare (`"backup": true` in `browser_targets.targets`)
  — they work exactly like any other channel if a sender happens to send their digit, they are
  just omitted from `帮助`/guidance text so an ordinary sender never stumbles onto them.
- any other text (not a digit, not `水印`, not `帮助`, not the private-channel passcode) gets a
  plain-language text reply instead of a placeholder image — see "Channels" below.
- capture failures return a generated `capture_error` image.
- message types listed in `ignore_message_types`, default `image`, are silently ignored when they
  have no channel to capture for (e.g. a non-text, non-image type from a sender with no channel).
- every photo a user sends to the bot is downloaded and archived under `incoming_image_dir`,
  organized by sender first and then by their currently joined channel
  (`{user_id}/channel_{id}/...`, or `{user_id}/channel_unassigned/...` before they've joined one)
  — the same `{user_id}/channel_{id}` layout outgoing screenshots use, so everything sent to and
  received from one sender lives together. See `src/screenshot_bot/workflow/README.md` →
  "Channels and photo capture". This archiving always happens, independent of whether that
  message also triggers a capture reply. Exception: a sender in the private channel (see
  "Channels" below) is archived under `private_channel.save_dir/{user_id}` instead, and never
  triggers a capture reply at all.
- WeChat POSTs are ACKed immediately; image work runs in a background thread.
- duplicate WeChat deliveries are dropped by `MsgId` dedupe.

## Channels

A "channel" is what earlier revisions of this doc called a "team" — the rename reflects how it
actually behaves: something a user *joins*, not a one-shot parameter on a single message. The set
of channel ids is entirely config-driven (`browser_targets.targets`, any string keys) — the
example config ships 5 regular channels plus 3 hidden backup channels (see "Backup channels"
below), but the count isn't hardcoded anywhere in the code.

- **Join**: send a bare digit for any configured channel. This both joins that channel (persisted
  per WeChat user in `runtime/user-team-tracker.json`, survives a restart) *and* immediately
  returns that channel's screenshot — one message does both, nothing separate to send. The very
  first time a sender joins any channel, a follow-up text tells them their images are archived
  under a folder named by their own user ID.
- **Re-capture**: once joined, send any photo to get that channel's screenshot back again,
  without resending the digit.
- **Not yet joined**: a photo from a sender with no prior digit gets a text prompt asking them to
  send a digit first.
- **Anything else unrecognized**: any other text a sender sends (not a digit, not a command) gets
  a plain-language reply stating their current channel (or that they haven't picked one) plus
  what to do next — see `src/screenshot_bot/workflow/help_text.py`'s `build_channel_guidance()`.
  This replaced a generated placeholder screenshot that told an actual end user nothing useful.
- **General help**: send `帮助` (or `help`) for an overview of all of the above, listing only the
  non-backup channels. Send `水印` for the watermark-customization commands specifically (see
  below).
- **Backup channels**: channels marked `"backup": true` in config work exactly like any other
  channel — joinable, capturable, re-capturable — but are omitted from `帮助`/guidance text, so
  they exist as spares without being advertised to ordinary senders.
- **Private channel**: hidden and passcode-gated. Sending `私密`/`private` does nothing (falls
  through to the same guidance reply as any unrecognized text) until that sender has first sent
  the exact passcode `11223344`, which unlocks private-channel access for them persistently. Once
  unlocked, `私密`/`private` joins a channel that is not tied to any capture target — every photo
  sent afterward is only archived, under `wechat_official_webhook.private_channel.save_dir`
  (default `storage/private`) in its own per-sender subfolder, with no screenshot captured or
  sent back. Send a channel digit to leave it. See `src/screenshot_bot/workflow/README.md` →
  "Private channel".

This is deliberately simple state — one key-value fact ("this WeChat user's current channel", plus
a private-channel-unlocked flag) via `UserTeamTracker`, not a multi-step guided conversation with
steps to get stuck in. All of the prompts above are written 傻瓜式 (plain-language, assumes no
technical background) — a sender messaging this bot may have no context beyond what it tells them
directly.

## Watermark customization

Each channel can customize its own watermark field text and background opacity over
chat, without touching `config.json` or affecting any other channel:

```text
水印 <频道> 状态                查看当前水印设置
水印 <频道> 设置 <序号> <内容>   修改水印第N行内容
水印 <频道> 透明度 <0-255>      设置背景不透明度 (0=全透明, 255=不透明)
水印 <频道> 重置                恢复默认水印设置
```

`watermark` works as an alias for `水印`. Each message is a complete, self-contained command —
there is no multi-step guided conversation or per-user session state to track. Overrides persist
across restarts in `browser_targets.watermark_settings_path` (default
`runtime/watermark-team-settings.json`) and only ever change the *value* of an existing field
(the label stays fixed); see `src/screenshot_bot/browser/README.md` → "Per-team watermark
customization" for the storage/merge details.

`水印 <频道> 设置 <序号>` — an index with nothing after it — clears that field's value to empty
rather than being treated as a malformed command; there is no way to type a literal empty string
as its own token, so omitting it is how a chat command expresses "blank this out." The two
example fields (`Test Area`, `Test Item`) default to empty values out of the box.

## Logs

`runtime/wechat-official-webhook-server.out.log` carries ad hoc console lines (WeChat API
responses, keep_alive/refresh failures, startup/warm_up summaries), each prefixed
`<ISO-8601 UTC timestamp> [tag] ...` (tags: `wechat`, `browser`, `startup`, `warmup`) so events
from different parts of the process can be correlated by time even when interleaved in one file.
`logs/wechat-official-webhook-events.jsonl` carries one structured JSON line per handled WeChat
message, field order `received_at`, `msg_type`, `touser`, `content`, ... , `ok` last — designed
to be skimmed left-to-right rather than requiring you to hunt through the object for the
timestamp or the final verdict. `total_latency` is the whole reply's wall-clock time; when it's
high, `capture_ms`/`watermark_ms` (nested under `capture_info`) cover the browser side and
`token_ms`/`upload_ms`/`send_ms` cover the three sequential WeChat API calls (access-token fetch,
media upload, message send) — each is timed individually so a slow reply can be attributed to a
specific step instead of being a single opaque total.

## Local Run

Copy secrets once:

```powershell
Copy-Item .\secrets.local.example.ps1 .\secrets.local.ps1
notepad .\secrets.local.ps1
```

Run only the local webhook:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Start-WebhookOnly.ps1 -ConfigPath .\config.example.json
```

For a production deployment, keep the existing tunnel pointed at `http://127.0.0.1:8790` (or
whatever port is configured) and don't start/stop it from here. For local testing, an optional
throwaway quick tunnel is available:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Start-PublicTunnel.ps1 -ConfigPath .\config.example.json
```

It prints a fresh `https://<random>.trycloudflare.com/wechat/official/webhook` URL each time —
paste that into the WeChat MP console (Settings & Development → Basic Configuration → Server
Configuration). Stop it with `scripts\Stop-PublicTunnel.ps1`.

## Module Contracts

Each capability module has its own README under `src/screenshot_bot/<module>/README.md`. Those files define the public API, inputs, outputs, dependencies, run method, test method, and examples. The workflow layer is the only layer that orchestrates multiple capabilities.
