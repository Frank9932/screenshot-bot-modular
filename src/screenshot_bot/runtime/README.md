# Runtime Utility Module

## Responsibility
Provide shared runtime utilities that have no business knowledge.

## Public API
- `utc_now_iso()`
- `MessageDedupe(ttl_seconds)`
- `JsonlLogger(path)`
- `write_latency_image(path, details)`

## Input
- Message keys for dedupe
- Event dictionaries for JSONL logging
- Image details for latency/error PNG generation

## Output
- Boolean first-seen result from dedupe
- JSONL log records
- Generated PNG files

## Dependencies
- Python standard library for clock, threading, JSONL, and TTL storage
- `Pillow` for generated latency/error images

## Run
This module is a library module. It has no long-running process.

## Test
```powershell
$env:PYTHONPATH="$PWD\src"
python - <<'PY'
from screenshot_bot.runtime.dedupe import MessageDedupe
d = MessageDedupe(60)
print(d.mark_first_seen('abc'), d.mark_first_seen('abc'))
PY
```

## Example
```python
from screenshot_bot.runtime.jsonl import JsonlLogger

JsonlLogger('logs/test.jsonl').write({'ok': True})
```
