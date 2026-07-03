# Browser Capability Module

## Responsibility
Capture a browser target through Chrome DevTools and apply watermarking.

## Public API
- `BrowserScreenshotService(config_path)`
- `BrowserScreenshotService.parse_team_id(text)`
- `BrowserScreenshotService.capture(team_id, output_dir=None, image_name=None, timeout_seconds=15)`
- `BrowserTargetConfig(config_path, config=None)`

## Input
- JSON config section: `browser_targets`
- Text command such as `1`, `2`, `3`
- Optional output directory and image file name

## Output
- PNG file path in `published_path`
- Capture metadata including target id, DevTools port, page title, page URL, capture time, and watermark data

## Dependencies
- Chrome with remote debugging enabled per target
- `websocket-client`
- `Pillow` for watermark rendering
- Shared config helpers only

## Run
This module is a library module. It is started by importing and calling the public API.

## Test
```powershell
$env:PYTHONPATH="$PWD\src"
python - <<'PY'
from screenshot_bot.browser import BrowserScreenshotService
svc = BrowserScreenshotService('config.example.json')
print(svc.parse_team_id('1'))
PY
```

## Example
```python
from screenshot_bot.browser import BrowserScreenshotService

svc = BrowserScreenshotService('config.example.json')
info = svc.capture('1', output_dir='screenshots')
print(info['published_path'])
```
