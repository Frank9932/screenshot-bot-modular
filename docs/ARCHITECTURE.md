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

`browser/profile_manager.py` owns Chrome process/profile lifecycle and DevTools port readiness.

`browser/devtools_client.py` owns Chrome DevTools protocol page selection and PNG capture.

`browser/watermark.py` owns PNG watermark rendering and has no transport knowledge.

`browser/screenshot_service.py` is the public browser screenshot API.

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

## WeChat Capability

`wechat/signature.py` verifies WeChat Official Account request signatures.

`wechat/xml_message.py` parses XML messages and builds stable dedupe keys from `MsgId` or fallback fields.

`wechat/official_api.py` owns WeChat Official Account API calls for access token, temporary media upload, and customer-service image send.

`wechat/image_sender.py` exposes a stable image-send API for workflows.

`wechat/webhook_server.py` owns HTTP webhook protocol, immediate POST ACK, background dispatch, and duplicate delivery dropping. It only calls an injected `message_processor.handle(...)` interface.

See `src/screenshot_bot/wechat/README.md` for the module contract.

## Workflow Layer

`workflow/wechat_image_reply.py` is the dispatcher for the current use case:

- text `1`, `2`, `3` captures the matching `browser_targets` Chrome DevTools target.
- if `virtual_desktop.enabled` is true, configured desktop numbers capture that desktop.
- message types listed in `capture_message_types` capture a desktop screenshot.
- non-capture text returns a generated `latency_test` image.
- capture failures return a generated `capture_error` image.
- message types listed in `ignore_message_types`, default `image`, are ignored unless they also trigger capture.
- duplicate WeChat deliveries are dropped by `MsgId` dedupe in the webhook layer.

See `src/screenshot_bot/workflow/README.md` for the module contract.

## Current Non-Goals

- No wx-cli.
- No desktop WeChat UI automation.
- No Cloudflare tunnel management.
- No LINE transport.
