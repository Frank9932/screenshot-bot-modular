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
    target_config.py       input number -> browser target
    profile_manager.py     Chrome profile lifecycle
    devtools_client.py     CDP page selection and screenshot
    watermark.py           PNG watermark rendering
    screenshot_service.py  browser screenshot use case
  desktop/
    screenshot_tool.py     ScreenshotTool.exe desktop capture wrapper
    virtual_desktop.py     optional Win+Ctrl virtual desktop switcher
  wechat/
    signature.py           WeChat signature verification
    xml_message.py         XML parsing and message keys
    official_api.py        access_token, media upload, image send
    image_sender.py        stable image-send API for workflows
    webhook_server.py      HTTP webhook server, ACK, dedupe, async work
  workflow/
    wechat_image_reply.py  dispatcher: message -> screenshot/latency image -> WeChat image reply
  runtime/
    clock.py
    dedupe.py
    jsonl.py
    latency_image.py
```


## Behavior

The WeChat webhook mirrors the LINE webhook routing model:

- text `1`, `2`, `3` captures the matching `browser_targets` Chrome DevTools target.
- if `virtual_desktop.enabled` is true, configured desktop numbers capture that desktop.
- message types listed in `capture_message_types` capture a desktop screenshot.
- non-capture text returns a generated `latency_test` image.
- capture failures return a generated `capture_error` image.
- message types listed in `ignore_message_types`, default `image`, are ignored unless they also trigger capture.
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
