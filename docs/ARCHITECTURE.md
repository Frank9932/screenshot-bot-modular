# Architecture

The test repo is organized as capability modules plus one workflow/dispatcher layer. Capability modules expose public APIs and do not reach into each other's internals. The workflow layer composes those APIs into the WeChat image reply use case.

## Dependency Direction

```text
scripts/
  -> workflow/
       -> browser/
       -> desktop/
       -> runtime/
       -> wechat/

wechat/webhook_server.py
  -> injected message_processor.handle(...) only
```

The WeChat webhook server owns HTTP protocol behavior, signature verification, immediate ACK, dedupe, async dispatch, and event logging. It does not decide whether a message captures a browser target, desktop, latency image, or error image.

## Browser Capability

`browser/target_config.py` parses `browser_targets` config and maps text such as `1`, `2`, `3` to target ids.

`browser/cdp_multi_tab_service.py` owns the low-level Chrome DevTools protocol: launching Chrome,
opening/tracking named tabs on one shared debug port, and capturing a tab's screenshot without
switching the foreground tab.

`browser/profile_manager.py` owns the single shared Chrome process lifecycle (one debug port,
one profile dir) and maps each `team_id` to its own named tab via `CdpMultiTabService`. A target
may declare `tab_count > 1` to open several tabs of itself; only tab 0 (`start_url`) logs in
(if the target has a `login` block), starts the session keep-alive ping, and starts the per-tab
background refresh loop — once, the first time that target's tab is seen by the current
process. Tabs 1..N-1 open directly at `app_url` and reuse tab 0's session with no login of
their own. On a process restart, `ensure_tab()` adopts each already-open tab by URL origin
instead of opening a duplicate (some login-gated sites reject a second concurrent login
attempt). It also closes Chrome's own default "New Tab" right after the first real tab exists
on a fresh launch (never before — closing a browser's only tab quits the whole process).

Several `team_id`s can share one physical multi-tab target by giving them identical
`name`/`start_url`/`app_url`/`tab_count`/`login` and only varying a `"tab"` field (e.g. WeChat
team numbers `1`-`5` each pinned to one tab of one login-gated site). `capture()` resolves
`tab` from that field when the caller doesn't pass one explicitly, so the workflow layer never
needs to know tabs exist. `BrowserScreenshotService.warm_up(team_ids=None)` opens/logs into each
requested team's own tab before the first real request (all of them if `team_ids` is omitted);
when several `team_id`s share a target name, only that target's session is established once
(not once per team_id), since a shared login attempted N times back-to-back races against
itself. Warming up one team never opens a *different* team's tab as a side effect, even when
they share a physical target — see `browser/README.md` → "Startup warm-up".

`browser/devtools_client.py` owns the shared low-level primitives (`http_json`, the raw
`DevToolsWebSocket` client) that `cdp_multi_tab_service.py` is built on.

`browser/watermark.py` owns PNG watermark rendering and has no transport knowledge.

`browser/watermark_settings.py` owns per-team overrides (`TeamWatermarkSettingsStore`) on top
of the global `watermark` config — a field's value or the background opacity, keyed by
`team_id`, persisted as one small JSON file. `resolve_watermark_config()` merges an override
onto the base config for one capture; nothing is ever mutated on the shared base config itself.

`browser/screenshot_service.py` is the public browser screenshot API: it ensures the shared
Chrome process and the target's tab (given a `team_id` and tab index) exist, captures via
`CdpMultiTabService`, saves the raw bytes through `screenshot_store.ScreenshotStore` under
`team_{team_id}/{user_id or target_name}/tab_{tab}/...` for audit (team first so all of one
team's captures are easy to find regardless of who requested them, then by requester when the
caller passes a `user_id`, e.g. the WeChat `FromUserName`), then watermarks the published copy.

See `src/screenshot_bot/browser/README.md` for the module contract.

## Desktop Capability

`desktop/screenshot_tool.py` wraps `ScreenshotTool.exe` and returns desktop screenshot metadata.

`desktop/virtual_desktop.py` optionally switches Windows virtual desktops and manages its local state/lock files.

See `src/screenshot_bot/desktop/README.md` for the module contract.

## Runtime Utility Capability

`runtime/dedupe.py` provides TTL message dedupe.

`runtime/jsonl.py` provides JSONL event logging.

`runtime/clock.py` provides timestamp helpers.

`runtime/console_log.py` provides `log_line(tag, message)` — every ad hoc console print used as
informal logging elsewhere in this codebase goes through this instead of a bare `print()`, so a
busy `server.out.log` can be scanned by timestamp and source (`wechat`, `browser`, `startup`,
`warmup`) instead of guessing from unlabeled text.

`runtime/latency_image.py` generates latency-test and capture-error PNGs.

See `src/screenshot_bot/runtime/README.md` for the module contract.

## Screenshot Store Capability

`screenshot_store/store.py` saves already-captured image bytes to
`storage/screenshots/{key}/YYYYMMDD_HHMMSS_mmm_{duration_ms}ms.png` under a caller-chosen key,
and returns a `ScreenshotRecord`. It does not call Chrome, does not call the WeChat API, and
does not parse user commands. Two capability modules use it for two different things, both
landing under one folder per channel: `browser/screenshot_service.py` calls it *twice* per
capture — `key = "channel_{team_id}/original"` for the pre-watermark bytes and
`key = "channel_{team_id}/watermarked"` for the exact bytes sent to WeChat, so either version can
be recovered later — and `workflow/wechat_image_reply.py` calls it once with
`key = "channel_{joined_channel_id or 'unassigned'}"` (archive of incoming photos WeChat users
send to the bot — see `workflow/README.md` → "Channels and photo capture" for how the joined
channel is tracked).

See `src/screenshot_bot/screenshot_store/README.md` for the module contract.

## WeChat Capability

`wechat/signature.py` verifies WeChat Official Account request signatures.

`wechat/xml_message.py` parses XML messages and builds stable dedupe keys from `MsgId` or fallback fields.

`wechat/official_api.py` owns WeChat Official Account API calls for access token, temporary media upload/download (`cgi-bin/media/get`), and customer-service image send.

`wechat/image_sender.py` exposes a stable image-send *and* text-send (`send_text`) API for
workflows, both sharing the same access-token-refresh-and-retry-once behavior.

`wechat/media_downloader.py` exposes a stable incoming-media-download API for workflows, with the
same retry-once-on-invalid-token behavior as `image_sender.py`.

`wechat/webhook_server.py` owns HTTP webhook protocol, immediate POST ACK, background dispatch, and duplicate delivery dropping. It only calls an injected `message_processor.handle(...)` interface.

See `src/screenshot_bot/wechat/README.md` for the module contract.

## Workflow Layer

`workflow/wechat_image_reply.py` is the dispatcher for the current use case:

- a bare `帮助`/`help` sends `workflow/help_text.py`'s `GENERAL_HELP_TEXT` via `send_text` and
  never reaches anything else below.
- text matching `workflow/watermark_commands.py`'s `水印`/`watermark` grammar is handled
  entirely as a settings command (parse -> mutate `browser/watermark_settings.py` -> text reply
  via `wechat/image_sender.py`'s `send_text`) and never reaches the capture dispatch below.
  Stateless by design: each message is one complete command, there is no per-user multi-step
  conversation to track.
- text `1`, `2`, `3`, ... joins that channel (persisted via `workflow/user_team_tracker.py`'s
  `UserTeamTracker`) *and* immediately captures its matching `browser_targets` Chrome DevTools
  target (several team_ids may share one physical multi-tab target — see "Browser Capability"
  above), passing the sender's `FromUserName` through as `user_id` for capture audit storage.
- an `image` message with no channel digit of its own is resolved via `UserTeamTracker` instead:
  a sender with a previously joined channel gets that channel re-captured and sent back (no need
  to resend the digit); a sender with none gets `CHANNEL_UNASSIGNED_PROMPT` as a text reply
  instead of reaching the capture dispatch. The photo itself is archived either way.
- if `virtual_desktop.enabled` is true, configured desktop numbers capture that desktop.
- message types listed in `capture_message_types` capture a desktop screenshot.
- non-capture text returns a generated `latency_test` image.
- capture failures return a generated `capture_error` image.
- message types listed in `ignore_message_types`, default `image`, are ignored unless they also trigger capture.
- an incoming `image` message's photo is downloaded via `wechat/media_downloader.py` and saved
  through `screenshot_store.ScreenshotStore` under `{incoming_image_dir}/{FromUserName}/...`
  (default `storage/incoming`), regardless of whether that message also triggers a capture reply.
  A download/save failure is recorded but does not block the reply.
- duplicate WeChat deliveries are dropped by `MsgId` dedupe in the webhook layer.

See `src/screenshot_bot/workflow/README.md` for the module contract.

## Current Non-Goals

- No wx-cli.
- No desktop WeChat UI automation.
- No *production* Cloudflare tunnel management (bring your own stable ingress for real use) —
  `ansible/tunnel-start.yml`/`tunnel-stop.yml`/`tunnel-status.yml` are optional convenience
  tooling for a throwaway quick tunnel, for testing only. See `ansible/README.md`.
- No LINE transport.
