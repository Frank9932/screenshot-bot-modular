# Screenshot Store Module

## Responsibility
Persist already-captured image bytes to disk under a caller-chosen key, and return metadata
about the saved file. It does not launch or drive Chrome, does not call the WeChat API, and
does not parse user/team text commands — callers pass it a storage key and raw image bytes.
The key is an arbitrary relative path segment, not necessarily a literal "tab" — two capability
modules use it for two different purposes:
- `browser/screenshot_service.py` calls it *twice* per capture — `key = "{user_id}/channel_{team_id}/original"`
  for the pre-watermark bytes and `key = "{user_id}/channel_{team_id}/watermarked"` for the exact
  bytes sent to WeChat — so each sender gets their own top-level folder, channel nested inside it,
  and either version of a capture can be recovered later. `user_id` falls back to `unknown` for
  callers that don't pass one (e.g. audit/demo scripts).
- `workflow/wechat_image_reply.py` keys it `{user_id}/channel_{joined_channel_id or 'unassigned'}`
  for incoming photos WeChat users send to the bot.

## Public API
- `ScreenshotStore(base_dir="storage/screenshots")`
- `ScreenshotStore.save_screenshot(tab_name: str, image_bytes: bytes, duration_ms: int) -> ScreenshotRecord`
- `ScreenshotRecord` — `tab_name`, `file_path`, `created_at`, `duration_ms`, `size_bytes`

## Input
- `tab_name`: directory (possibly multi-segment, e.g. `"oUser123/tab_2"`) under `base_dir` the
  screenshot belongs to — despite the parameter name, callers may pass any storage key
- `image_bytes`: PNG bytes already captured elsewhere
- `duration_ms`: how long the capture took, embedded in the file name

## Output
- PNG file written to `{base_dir}/{tab_name}/YYYYMMDD_HHMMSS_mmm_{duration_ms}ms.png`
- `ScreenshotRecord` describing the saved file (path, capture time, duration, size in bytes)

## Dependencies
- Python standard library only (`pathlib`, `datetime`, `dataclasses`)

## Run
This module is a library module. It is started by importing and calling the public API.

## Test
```powershell
$env:PYTHONPATH="$PWD\src"
python - <<'PY'
from screenshot_bot.screenshot_store import ScreenshotStore
store = ScreenshotStore(base_dir="runtime/screenshot-store-test")
record = store.save_screenshot("tradingview", b"fake-png-bytes", duration_ms=84)
print(record.file_path)
PY
```

## Example
```python
from screenshot_bot.screenshot_store import ScreenshotStore

store = ScreenshotStore()
record = store.save_screenshot("oWeChatUser123/channel_1/watermarked", image_bytes, duration_ms=84)
print(record.file_path)       # storage/screenshots/oWeChatUser123/channel_1/watermarked/20260704_101530_238_84ms.png
print(record.size_bytes)
```
