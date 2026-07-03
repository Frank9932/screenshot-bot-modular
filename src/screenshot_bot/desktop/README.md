# Desktop Capability Module

## Responsibility
Capture the Windows desktop and optionally switch virtual desktops before capture.

## Public API
- `DesktopScreenshotService(config_path, screenshot_tool='ScreenshotTool.exe', screenshot_dir='screenshots')`
- `DesktopScreenshotService.capture(output_dir=None, image_name=None, timeout_seconds=15)`
- `VirtualDesktopSwitcher(config=None, base_dir=None)`
- `VirtualDesktopSwitcher.switch_to(target_desktop)`
- `VirtualDesktopSwitcher.exclusive_session()`
- `parse_desktop_number(text, config=None)`

## Input
- JSON config sections: `wechat_official_webhook`, `virtual_desktop`
- Optional desktop number text
- Optional output directory and image file name

## Output
- PNG file path in `published_path`
- Capture metadata and virtual desktop switch metadata

## Dependencies
- `ScreenshotTool.exe` for desktop screenshot capture
- `pyautogui` only when virtual desktop switching is enabled
- Windows locking API through `msvcrt`

## Run
This module is a library module. It can be called without WeChat or LINE.

## Test
```powershell
$env:PYTHONPATH="$PWD\src"
python - <<'PY'
from screenshot_bot.desktop import parse_desktop_number
print(parse_desktop_number('2'))
PY
```

## Example
```python
from screenshot_bot.desktop import DesktopScreenshotService

svc = DesktopScreenshotService('config.example.json')
info = svc.capture(output_dir='screenshots')
print(info['published_path'])
```
