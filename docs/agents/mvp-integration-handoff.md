# MVP Integration Handoff

- Task: Project-level MVP Integration (see `docs/TASK_STATUS.md` Task 14)
- Owner: Integration Agent
- Date: 2026-07-20
- Status at handoff: local dev + local validation complete; not committed, not reviewed, no live
  environment verification

## Goal

Per the "Project-level MVP Integration Sprint" instructions: assemble, from already-existing
modules only, one real vertical business chain (WeChat message -> router -> equipment catalog ->
numbered clarification -> confirm -> browser/CDP capture -> storage -> WeChat reply) that is
runnable, demoable, and repeatable — without rewriting existing modules or expanding scope.

## What Was Found (audit, before any code was written)

Read, in order: `docs/PROJECT_RULES.md`, `docs/PROJECT_SNAPSHOT.md`, `docs/TASK_STATUS.md`,
`docs/KNOWLEDGE_RECONCILIATION.md`, `docs/STABILIZATION_PLAN.md` (all as of their 2026-07-20
snapshot), then the actual current code.

**Environment note, worth flagging explicitly**: this session started in a separate git worktree
(`.claude/worktrees/integration-agent-f4c944`, branch `claude/integration-agent-f4c944`, based on
`master`). That worktree has none of the equipment-catalog/router/menu code, and none of the five
docs above — they only exist as **uncommitted changes** in the main worktree
(`C:\Users\frank\screenshot-bot-modular`, branch `feature/user-scoped-storage-and-channels`,
tip `cbcc8ce` + 18 modified/13 untracked files on top). All work described below was done in that
main worktree, since that's the only place the "already-existing modules" the brief refers to
actually exist. No files in the isolated `integration-agent-f4c944` worktree were touched.

**Central finding**: the requested MVP chain is **already fully implemented**, not partially. The
single orchestrator entrypoint `WeChatImageReplyWorkflow.handle()`
(`src/screenshot_bot/workflow/wechat_image_reply.py:86`) already composes, for real, every stage
in the brief's target chain:

| Stage | Existing Module | Integration Status | Evidence |
|---|---|---|---|
| WeChat webhook entry | `wechat/webhook_server.py` (`WeChatWebhookServer`) | Already wired | `workflow/wechat_image_reply.py:427` `build_wechat_official_server` constructs it with `workflow.handle` injected as `message_processor` |
| Message routing | `workflow/message_router.py` (`route_message`, pure function) | Already wired | called at `wechat_image_reply.py:141` |
| Equipment catalog lookup | `workflow/equipment_catalog.py` (`load_categories`/`load_equipment`) | Already wired | called at `wechat_image_reply.py:370-382`; real data at `runtime/cdp-explore-out/hvac_equipment.csv` (676 rows, scraped from the live WebStation by `scripts/crawl_graphics_tree.py`) |
| Numbered clarification | `workflow/equipment_prompts.py` (`build_category_list_text`/`build_equipment_list_text`) + `message_router.py` digit-index resolution | Already wired | `message_router.py:141-154` |
| Selection session state | `workflow/equipment_selection_tracker.py` (`EquipmentSelectionTracker`) | Already wired | persists per-sender stage across restarts, `wechat_image_reply.py:74` |
| Channel/target resolution | `workflow/user_team_tracker.py` (`UserTeamTracker`) | Already wired | `wechat_image_reply.py:61` |
| Browser/CDP capture | `browser/screenshot_service.py` (`BrowserScreenshotService.capture`), `browser/equipment_navigation.py` (`navigate_to_equipment_graphic`) | Already wired | `capture()`'s `equipment_path` param calls `profile_manager.service.navigate_equipment` before screenshotting, `screenshot_service.py:107-115` |
| Storage | `screenshot_store/store.py` (`ScreenshotStore`) | Already wired | `screenshot_service.py:129-131,154-156` |
| WeChat reply | `wechat/image_sender.py` (`WeChatImageSender`) | Already wired | `wechat_image_reply.py:308` |

Nothing above needed new glue code. The flow is gated behind `equipment_catalog.enabled` (default
`false` in `config.example.json`) — the code path is real, just not turned on by default, and
(per `docs/TASK_STATUS.md` Task 8, already `Blocked` before this session) never verified against
a real WeChat account.

## What Was Done This Session

1. **Audit only, no code changes** (steps above).
2. **`scripts/demo_mvp.py`** (new) — drives the real `WeChatImageReplyWorkflow.handle()` with a
   fake WeChat message, so the real router/catalog/tracker/storage all run. Only two stand-ins:
   `DemoSender` (prints instead of calling the WeChat API) and `DemoBrowser` (renders a local
   placeholder PNG via the already-existing `runtime.latency_image.write_latency_image` instead
   of driving real Chrome, but persists it through a real `ScreenshotStore`). See
   `docs/MVP_DEMO.md` for full behavior and the deviation from the brief's illustrative free-text
   example.
3. **`config.mvp_demo.json`** (new) — demo-only config: `equipment_catalog.enabled: true`, all
   paths redirected under `runtime/mvp-demo/` (already gitignored via `/runtime/`) so the demo
   never touches real `runtime/`/`storage/` state.
4. **`docs/MVP_DEMO.md`** (new) — demo write-up: goal, level reached, run instructions, what it
   does, known limitations.
5. **This handoff file** (new).
6. **`docs/TASK_STATUS.md`** — one row appended (Task 14), no other edits to that file.

No other files were modified. `desktop/`, `browser/`, `wechat/`, `workflow/message_router.py`,
`equipment_catalog.py`, etc. were **not touched** — only read.

## Testing / Validation

Ran `scripts/demo_mvp.py` twice (first run surfaced and fixed a real bug: Windows console
`cp1252` stdout can't encode the Chinese reply text — fixed with
`sys.stdout.reconfigure(encoding="utf-8")`; second run was clean, exit code 0). Verified on disk
afterward (not just console output) that:
- `runtime/mvp-demo/storage/demo-user-001/channel_1/original/` has 2 real PNGs (plain-channel
  capture + equipment capture)
- `runtime/mvp-demo/storage/demo-user-006/channel_2/original/` has 1 real PNG (the simulated
  browser-failure turn correctly produced *no* store write, matching production's
  `_run_capture` except-branch behavior)
- `runtime/mvp-demo/user-team-tracker.json` and `equipment-selection-tracker.json` hold correct,
  real persisted state (including the real CSV-derived hash-route `path` for the confirmed
  equipment)

| Validation | Command | Result | Evidence |
|---|---|---|---|
| Full local demo runs end-to-end | `PYTHONPATH="$PWD/src" python scripts/demo_mvp.py` | Passed | Console transcript, no traceback, exit 0 |
| Unique-channel capture (non-equipment path unaffected) | Step 1 in demo | Passed | `ok=True trigger_kind=browser_target` |
| Multi-candidate clarification (category + equipment lists) | Steps 2-4 | Passed | Real 7-category, real 52-item lists printed |
| User resolves by number | Steps 3-4 | Passed | Correct category/equipment selected |
| Confirm + capture + storage + reply | Steps 5-6 | Passed | Real file written, verified on disk |
| Invalid selection index | Edge 1b | Passed | Re-prompt, stage unchanged (`awaiting_category`) |
| Capture requested with no context | Edge 2 | Passed | "not ready" reply, no capture attempted |
| Bare digit, no active flow | Edge 3 | Passed | Falls to guidance, not misread as equipment index |
| Missing/empty catalog | Edge 4 | Passed | Empty-catalog fallback text, no crash |
| Simulated browser/CDP failure | Edge 5b | Passed | `ok=True trigger_kind=capture_error`, error-placeholder image generated, no crash |
| Storage-failure path | — | **Not Run** | Not exercised — would need to inject a broken `ScreenshotStore`; out of scope for this pass, flagged as a gap |
| Live WeChat round trip | — | **Not Run / Blocked** | No live credentials, no authorization to contact real WeChat API from an unattended demo |
| Live Chrome/CDP against WebStation | — | **Not Run / Blocked** | No network reachability / login credentials in this session; `10.121.0.14` is internal-only |

No automated test suite was added (matches `docs/TASK_STATUS.md` Task 5's own scope: test
baseline is a separate, not-yet-started task, and this sprint's rules explicitly said not to
build one now).

## Known Risks

- **P1**: The demo's realism ceiling is the mocked Chrome/CDP boundary — a real login failure,
  session-timeout, or DOM-shape change on the live WebStation site would not be caught by this
  demo. This is the same gap `docs/TASK_STATUS.md` Task 8 already tracks; not new.
- **P2**: `equipment_catalog.enabled` staying `false` by default in `config.example.json` means a
  fresh deployment from that template alone would not expose this flow — this is an existing,
  intentional default (per `workflow/README.md`), not something this session changed.
- **P2**: The brief's illustrative free-text query example ("发送 RYG1 MVSB") doesn't match the
  actual category/equipment picker UX. Documented explicitly in `docs/MVP_DEMO.md` section 2 so
  no future reader assumes free-text search exists.

## Next Step

Get the project owner's decision on whether/how to attempt Level B/A verification (needs real
WeChat credentials + explicit authorization to contact the live API, real Chrome + network
reachability to `10.121.0.14`) — this session cannot and should not do that unattended. This
mirrors `docs/TASK_STATUS.md` Task 8's existing, still-open "Next Step".
