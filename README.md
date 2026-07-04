# Screenshot Bot Modular

Modular WeChat Official Account webhook flow with LINE-compatible routing behavior, refactored
out of [screenshot-bot](https://github.com/Frank9932/screenshot-bot) into capability modules.

This repo intentionally excludes:

- wx-cli
- desktop WeChat polling
- UI-driven WeChat sending
- Cloudflare tunnel creation or control

The tunnel must stay external. This repo only runs the local HTTP server behind whatever tunnel
is already forwarding to it (see `ansible/README.md` for the deployed default port).

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

The WeChat webhook mirrors the LINE webhook routing model:

- text `1`, `2`, `3`, ... captures the matching `browser_targets` Chrome DevTools target — several
  team numbers may share one physical multi-tab site, each pinned to its own tab (see
  `src/screenshot_bot/browser/README.md` → "Team-per-tab targets"); the sender is passed through
  so that target's audit copy is organized by requester.
- if `virtual_desktop.enabled` is true, configured desktop numbers capture that desktop.
- message types listed in `capture_message_types` capture a desktop screenshot.
- non-capture text returns a generated `latency_test` image.
- capture failures return a generated `capture_error` image.
- message types listed in `ignore_message_types`, default `image`, are ignored unless they also trigger capture.
- images users send to the bot are downloaded and saved under `incoming_image_dir` (per-sender
  directory), independent of whether that message also triggers a capture reply.
- WeChat POSTs are ACKed immediately; image work runs in a background thread.
- duplicate WeChat deliveries are dropped by `MsgId` dedupe.

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

Do not start or stop Cloudflare from this repo. Keep the existing tunnel pointed at:

```text
http://127.0.0.1:8790
```

WeChat Official Account URL:

```text
https://<current-tunnel-host>/wechat/official/webhook
```

## Module Contracts

Each capability module has its own README under `src/screenshot_bot/<module>/README.md`. Those files define the public API, inputs, outputs, dependencies, run method, test method, and examples. The workflow layer is the only layer that orchestrates multiple capabilities.
