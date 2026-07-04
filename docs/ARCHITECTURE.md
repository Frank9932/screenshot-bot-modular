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
needs to know tabs exist. `BrowserScreenshotService.warm_up()` opens/logs into every configured
target before the first real request; when several `team_id`s share a target name, it only
does that work once (not once per team_id), since a shared login attempted N times back-to-back
races against itself.

`browser/devtools_client.py` owns the shared low-level primitives (`http_json`, the raw
`DevToolsWebSocket` client) that `cdp_multi_tab_service.py` is built on.

`browser/watermark.py` owns PNG watermark rendering and has no transport knowledge.

`browser/screenshot_service.py` is the public browser screenshot API: it ensures the shared
Chrome process and the target's tab (given a `team_id` and tab index) exist, captures via
`CdpMultiTabService`, saves the raw bytes through `screenshot_store.ScreenshotStore` under
`{user_id or target_name}/tab_{tab}/...` for audit (organized by requester when the caller
passes a `user_id`, e.g. the WeChat `FromUserName`), then watermarks the published copy.

See `src/screenshot_bot/browser/README.md` for the module contract.

## Desktop Capability

`desktop/screenshot_tool.py` wraps `ScreenshotTool.exe` and returns desktop screenshot metadata.

`desktop/virtual_desktop.py` optionally switches Windows virtual desktops and manages its local state/lock files.

See `src/screenshot_bot/desktop/README.md` for the module contract.

## Runtime Utility Capability

`runtime/dedupe.py` provides TTL message dedupe.

`runtime/jsonl.py` provides JSONL event logging.

`runtime/clock.py` provides timestamp helpers.

`runtime/latency_image.py` generates latency-test and capture-error PNGs.

See `src/screenshot_bot/runtime/README.md` for the module contract.

## Screenshot Store Capability

`screenshot_store/store.py` saves already-captured image bytes to
`storage/screenshots/{key}/YYYYMMDD_HHMMSS_mmm_{duration_ms}ms.png` under a caller-chosen key,
and returns a `ScreenshotRecord`. It does not call Chrome, does not call the WeChat API, and
does not parse user commands. Two capability modules use it for two different things:
`browser/screenshot_service.py` calls it on every capture with
`key = "{user_id or target_name}/tab_{tab}"` (audit trail for outgoing screenshots), and
`workflow/wechat_image_reply.py` calls it with `key = "{FromUserName}"` (archive of incoming
photos WeChat users send to the bot).

See `src/screenshot_bot/screenshot_store/README.md` for the module contract.

## WeChat Capability

`wechat/signature.py` verifies WeChat Official Account request signatures.

`wechat/xml_message.py` parses XML messages and builds stable dedupe keys from `MsgId` or fallback fields.

`wechat/official_api.py` owns WeChat Official Account API calls for access token, temporary media upload/download (`cgi-bin/media/get`), and customer-service image send.

`wechat/image_sender.py` exposes a stable image-send API for workflows.

`wechat/media_downloader.py` exposes a stable incoming-media-download API for workflows, with the
same retry-once-on-invalid-token behavior as `image_sender.py`.

`wechat/webhook_server.py` owns HTTP webhook protocol, immediate POST ACK, background dispatch, and duplicate delivery dropping. It only calls an injected `message_processor.handle(...)` interface.

See `src/screenshot_bot/wechat/README.md` for the module contract.

## Workflow Layer

`workflow/wechat_image_reply.py` is the dispatcher for the current use case:

- text `1`, `2`, `3`, ... captures the matching `browser_targets` Chrome DevTools target (several
  team_ids may share one physical multi-tab target — see "Browser Capability" above), passing
  the sender's `FromUserName` through as `user_id` for capture audit storage.
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
- No Cloudflare tunnel management.
- No LINE transport.
