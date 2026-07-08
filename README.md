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
port). For testing, `scripts/Start-PublicTunnel.ps1`/`Stop-PublicTunnel.ps1` (and their
`ansible/tunnel-*.yml` wrappers) are provided as optional convenience tooling for a throwaway
Cloudflare quick tunnel — see "Local Run" below.

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
  desktop/
    screenshot_tool.py     ScreenshotTool.exe desktop capture wrapper
    virtual_desktop.py     optional Win+Ctrl virtual desktop switcher
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
- text `1`, `2`, `3`, `4`, `5` **joins that channel and immediately captures its screenshot** —
  several channel numbers may share one physical multi-tab site, each pinned to its own tab (see
  `src/screenshot_bot/browser/README.md` → "Team-per-tab targets"); the output filename is
  prefixed `channel{id}-...`, and both the watermarked and original (pre-watermark) bytes are
  archived, under `channel_{id}/watermarked/...` and `channel_{id}/original/...` respectively.
- once a sender has joined a channel this way, **sending a photo captures and returns that
  channel's screenshot again** — no need to resend the digit each time. A photo from someone who
  has never joined a channel gets a text prompt telling them to send a digit first, instead of
  being silently ignored. See "Channels" below.
- if `virtual_desktop.enabled` is true, configured desktop numbers capture that desktop
  (filename prefixed `desktop{n}-...`).
- message types listed in `capture_message_types` capture a desktop screenshot.
- non-capture text returns a generated `latency_test` image.
- capture failures return a generated `capture_error` image.
- message types listed in `ignore_message_types`, default `image`, are ignored unless they also trigger capture.
- every photo a user sends to the bot is downloaded and archived under `incoming_image_dir`,
  organized by the sender's currently joined channel (`channel_{id}/...`, or
  `channel_unassigned/...` before they've joined one) — see `src/screenshot_bot/workflow/README.md`
  → "Channels and photo capture". This archiving always happens, independent of whether that
  message also triggers a capture reply.
- WeChat POSTs are ACKed immediately; image work runs in a background thread.
- duplicate WeChat deliveries are dropped by `MsgId` dedupe.

## Channels

A "channel" (`1`-`5`) is what earlier revisions of this doc called a "team" — the rename reflects
how it actually behaves: something a user *joins*, not a one-shot parameter on a single message.

- **Join**: send a bare digit `1`-`5`. This both joins that channel (persisted per WeChat user in
  `runtime/user-team-tracker.json`, survives a restart) *and* immediately returns that channel's
  screenshot — one message does both, nothing separate to send.
- **Re-capture**: once joined, send any photo to get that channel's screenshot back again,
  without resending the digit.
- **Not yet joined**: a photo from a sender with no prior digit gets a text prompt asking them to
  send a digit first.
- **General help**: send `帮助` (or `help`) for an overview of all of the above. Send `水印` for
  the watermark-customization commands specifically (see below).

This is deliberately simple state — one key-value fact ("this WeChat user's current channel") via
`UserTeamTracker`, not a multi-step guided conversation with steps to get stuck in.

## Watermark customization

Each channel (`1`-`5`) can customize its own watermark field text and background opacity over
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
timestamp or the final verdict.

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
