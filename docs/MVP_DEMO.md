# MVP Demo

- Version: 0.1
- Status: Draft (code complete, local-only validation; no live WeChat/Chrome/BMS verification)
- Owner: Integration Agent
- Last Updated: 2026-07-20

## 1. MVP Goal

Show one real, repeatable, end-to-end business chain for this project:

```
WeChat message -> webhook -> message router -> equipment catalog lookup
  -> numbered clarification (if >1 candidate) -> user picks a number
  -> confirm -> browser/CDP capture -> watermark -> storage -> WeChat image reply
```

## 2. What This Actually Is (important)

**No new orchestrator was written.** Auditing the repo (see `docs/PROJECT_SNAPSHOT.md`,
`docs/KNOWLEDGE_RECONCILIATION.md`, and the code itself) found that this entire chain already
exists and is already wired together in one place:
`src/screenshot_bot/workflow/wechat_image_reply.py`'s `WeChatImageReplyWorkflow.handle()` —
the exact function the live webhook calls for every incoming message. It already composes, for
real:

- `message_router.route_message()` — pure decision function (channel join, watermark commands,
  private channel, and the full select-equipment state machine)
- `equipment_catalog.load_categories()` / `.load_equipment()` — reads the real equipment CSV
  (`runtime/cdp-explore-out/hvac_equipment.csv`, 676 real rows scraped from the production
  WebStation dashboard by `scripts/crawl_graphics_tree.py` / `scripts/screenshot_equipment_list.py`)
- `EquipmentSelectionTracker` — persists each sender's category -> equipment -> confirm progress
- `UserTeamTracker` — persists each sender's joined channel
- `BrowserScreenshotService.capture(..., equipment_path=...)` — reroutes the channel's tab to the
  equipment's graphic (`CdpMultiTabService.navigate_equipment`, via
  `browser/equipment_navigation.py`) before screenshotting
- `ScreenshotStore` — persists the captured bytes under `{user_id}/channel_{id}/{original,watermarked}`
- `WeChatImageSender` — sends the reply back

This MVP integration's job was therefore **audit + demo + gap analysis**, not new glue code.
The one new thing is `scripts/demo_mvp.py`, which drives the real `handle()` entrypoint with a
fake WeChat message so the whole chain runs locally and repeatably. See
`docs/agents/mvp-integration-handoff.md` for the full audit trail.

**Deviation from the illustrative example in the original task brief**: the brief's example
dialogue ("发送 RYG1 MVSB" free-text query, multi-candidate response) implies fuzzy/free-text
matching against equipment names. The code that already exists does **not** do free-text search —
it's a deterministic two-level picker (`设备` -> numbered category list -> numbered equipment
list -> confirm -> `获取截图`). Per project rule ("不要允许仅凭 LLM 猜测唯一设备" / prefer
deterministic logic when the catalog + rules already suffice, and reuse existing code over
rewriting), this demo uses the real, already-implemented picker rather than building a new
free-text search feature. It satisfies the same underlying requirement — ambiguous input resolved
via a numbered list the user picks from, with session state that survives a restart — just via a
different (already-built, already-documented) UX shape.

## 3. Level Reached

**Level C — Local End-to-End Demo.**

| Level | Reached? | Why |
|---|---|---|
| A (Full Live) | No | Would need a real WeChat account/session, a real Chrome process with an authenticated CDP session against `10.121.0.14` (internal-only IP, production dashboard), and permission to send real WeChat messages. None of that is available/authorized in this session. |
| B (Hybrid) | No | Same blockers as A minus the browser: sending a real WeChat reply still requires live WECHAT_* credentials and an explicit user go-ahead to contact the real API (out of scope for an unattended demo). |
| C (Local Demo) | **Yes** | `scripts/demo_mvp.py` drives the real orchestrator with a fake WeChat message; real router/catalog/tracker/storage; only the WeChat API call and the Chrome/CDP tab are stand-ins. |

## 4. Run It

Dependencies: Python 3.12 (confirmed working — `Python 3.12.10`), `Pillow` (already a project
dependency, confirmed importable). No Chrome, no network, no WeChat credentials needed.

```powershell
$env:PYTHONPATH = "$PWD\src"
python scripts\demo_mvp.py
```

(Bash/WSL equivalent: `PYTHONPATH="$PWD/src" python scripts/demo_mvp.py`)

No config edits needed — the demo uses its own `config.mvp_demo.json` (equipment catalog enabled,
all state redirected under `runtime/mvp-demo/`, which is already covered by the repo's
`/runtime/` gitignore rule). Delete `runtime/mvp-demo/` any time to reset demo state; the script
also works fine on a clean run.

## 5. What It Does

Prints a scripted conversation for `demo-user-001`, then five edge-case turns for other demo
users, all through the same live workflow instance:

1. `1` — joins channel 1 (also a real plain-channel capture — shows the non-equipment path still
   works unmodified)
2. `设备` — starts the select-equipment flow, returns the real 7-category list from the CSV
3. `3` — picks category 3 (`RYG1 - DHU`, 52 real equipment rows), returns the numbered list
4. `2` — picks equipment 2 (`DHU-DH01-02-RYG1A-F1`), returns a confirm prompt
5. `确认` — confirms the selection
6. `获取截图` — triggers the capture: `BrowserScreenshotService.capture(..., equipment_path=...)`
   equivalent runs (mocked at the Chrome/CDP boundary only), the resulting image bytes go through
   a real `ScreenshotStore.save_screenshot()`, and a reply is "sent" (printed)

Then, same running instance, no separate test harness:
- out-of-range category digit -> re-prompt with the same list
- `获取截图` with nothing confirmed yet -> "not ready" reply
- a bare digit with no channel/flow context -> falls through to ordinary guidance text (not
  misread as an equipment index)
- equipment CSV temporarily pointed at a missing path -> empty-catalog fallback text, not a crash
- simulated browser/CDP failure -> the real error path (`_run_capture`'s `except` branch) fires:
  `ok=True`, `trigger_kind="capture_error"`, an error-placeholder image is still generated and
  "sent", exactly as production behaves when a live capture fails

## 6. Expected Output / Generated Files

Console output shows every "sent" WeChat message inline. Files land under `runtime/mvp-demo/`
(gitignored):
- `runtime/mvp-demo/screenshots/*.png` — the final "reply" images (placeholder content, real PNG
  files, real filenames matching production's `channel{id}[-equipment-{name}]-{ts}-{uuid}.png`
  convention)
- `runtime/mvp-demo/storage/{user}/channel_{id}/original/*.png` — real `ScreenshotStore` output
- `runtime/mvp-demo/user-team-tracker.json` — real persisted channel-join state
- `runtime/mvp-demo/equipment-selection-tracker.json` — real persisted per-user selection stage

## 7. Known Limitations

- No live WeChat, Chrome, or BMS verification — see "Level Reached" above and Task 8/9/10 in
  `docs/TASK_STATUS.md`, which were already `Blocked` on exactly this before this session and
  remain so.
- No free-text equipment search — see "Deviation" in section 2.
- Storage-failure (disk-full/permission-denied) is not exercised in the demo; everything else in
  the brief's suggested scenario list is (see `docs/agents/mvp-integration-handoff.md` for the
  validation table).
- The demo's `DemoBrowser`/`DemoSender` are new, demo-only stand-ins (not reused from
  `workflow/README.md`'s existing `MockBrowser`/`MockSender` snippet) because the equipment-flow
  path needs kwargs (`equipment_path`, etc.) and a real `ScreenshotStore` write that snippet's
  minimal mocks don't cover — this is additive, it doesn't replace or duplicate that snippet's
  purpose (which is a quick copy-paste REPL check, not a scripted demo).

## 8. Next Steps to Reach a Higher Level

To reach Level B/A: a session with real `WEBSTATION_USERNAME`/`WEBSTATION_PASSWORD`, network
reachability to `10.121.0.14`, a running Chrome with CDP enabled, and real
`WECHAT_APPID`/`WECHAT_APPSECRET`/`WECHAT_OFFICIAL_WEBHOOK_TOKEN` plus explicit authorization to
contact the live WeChat API — none of which this session has or should assume. This matches
`docs/TASK_STATUS.md` Task 8's existing "Next Step": schedule real-environment verification once a
test baseline exists.
