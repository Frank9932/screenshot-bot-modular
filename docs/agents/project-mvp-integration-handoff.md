# Project MVP Integration Report

- Task: Project-level MVP Integration — final verification/stabilization pass across the
  Workflow MVP, Browser MVP, and Storage/Reply MVP (all three already `Review`, see
  `docs/TASK_STATUS.md`)
- Owner: Final Integration Agent
- Date: 2026-07-20
- Status at handoff: **integration verified, no new integration defects found, no code
  changes made this session**; not committed, not merged, no live-environment verification

## Environment note

Same standing situation every prior handoff in this repo records: all work happened directly
in the main checkout (`C:\Users\frank\screenshot-bot-modular`, branch
`feature/user-scoped-storage-and-channels`, tip `cbcc8ce` + the uncommitted working-tree
changes already produced by the three module-level MVP sessions). No worktree was created, no
branch was switched, nothing was committed or merged, per this session's explicit instructions.

## 1. Scope of This Session

This was **not** a new development pass. The three module-level sessions
(`docs/agents/workflow-mvp-handoff.md`, `docs/agents/browser-mvp-handoff.md`,
`docs/agents/storage-reply-mvp-handoff.md`) had each already audited their own segment,
documented its contract, fixed the real defects they found, and added unit tests. This
session's job was to verify the *seams between* those three segments still agree with each
other now that all three sets of changes coexist in the same working tree, run the full
validation suite, and confirm nothing was missed or has regressed. **Zero additional code
changes were made** — the audit found the three prior sessions' contract work to already be
internally consistent end-to-end.

## 2. Integration Diagram / Actual Execution Chain

```
WeChat POST (or menu tap)
  -> wechat/webhook_server.py: WeChatWebhookHandler.do_POST
       - verifies signature, parses XML, dedupes by MsgId
       - spawns a daemon thread -> _process_async
       -> message_processor.handle(message, received_at, started)
            (message_processor is the injected WeChatImageReplyWorkflow instance;
             this is the one call site the entire chain below hangs off of)

WeChatImageReplyWorkflow.handle()  [workflow/wechat_image_reply.py]
  1. Menu-tap translation: an "event"/"CLICK" message's EventKey is translated back into the
     same plain text a typed command would have sent (workflow/menu.py: event_key_to_text),
     so every branch below never has to know menu taps exist.
  2. Incoming "image" messages are archived (best-effort, never blocks the reply) via
     _store_incoming_image -> ScreenshotStore.save_screenshot, before routing continues.
  3. State fetch: UserTeamTracker.get_team/has_unlocked_private (channel/private-unlock),
     and, only if equipment_catalog is enabled, EquipmentSelectionTracker.get +
     equipment_catalog.load_categories/load_equipment (the CSV-backed category/equipment
     lists) — all I/O is done here, ahead of time, so the next step stays pure.
  4. message_router.route_message(...) — a pure function; decides one of ~20 "kind"s
     (general_help, join_channel, equipment_start, equipment_capture, ignored, etc.) with zero
     side effects.
  5. .handle() dispatches on action["kind"], executing the corresponding side effect:
     persist channel/equipment-tracker state, then either reply with plain text
     (image_sender.send_text) or trigger a capture:
       -> BrowserScreenshotService.capture(channel_id, equipment_path=..., ...)
            [browser/screenshot_service.py]
            - BrowserProfileManager.ensure_tab (Chrome/CDP provisioning + login)
            - equipment_navigation.navigate_to_equipment_graphic (if equipment_path given)
            - CdpMultiTabService.screenshot -> raw PNG bytes
            - ScreenshotStore.save_screenshot (pre-watermark audit copy)
            - WatermarkRenderer.apply -> watermarked PNG
            - ScreenshotStore.save_screenshot (post-watermark audit copy)
            - returns a dict: published_path, store_path, capture_ms, page_title/url, ...
       -> _send_capture_reply -> WeChatImageSender.send_image_file(touser, published_path)
            [wechat/image_sender.py] -> WeChatOfficialClient (access token -> upload -> send)
  6. Every path returns a normal `result` dict back through .handle() — capture() failures,
     storage-layer failures propagating through capture(), and sender failures are all folded
     into result["ok"]/result["capture_error"]/result["send_error"] rather than raised.
  <- back to _process_async: result (plus dedupe_key) is written to the JSONL event log.
```

Cross-cutting: `WeChatWebhookHandler._process_async`'s own `except Exception` is the outermost
safety net — even a `.handle()` bug this project's own tests didn't anticipate cannot crash the
webhook process, only that one request's log line degrades to a thinner shape.

## 3. Interfaces Verified

Every hand-off point in the diagram above was checked both by reading the producer and every
consumer side by side, and by the existing/expanded test suite:

| Seam | Producer | Consumer(s) | Verified |
|---|---|---|---|
| WeChat message -> workflow | `WeChatWebhookServer`/`_process_async` | `WeChatImageReplyWorkflow.handle(message, received_at, started)` | Signature matches exactly; outer `except Exception` confirmed present and unmodified. |
| Menu tap -> plain text | `workflow/menu.py` (`build_menu_payload`, `event_key_to_text`) | `.handle()`'s CLICK-event translation | Every `EventKey` constant `menu.py` emits (`MENU_HELP_KEY`, `MENU_WATERMARK_HELP_KEY`, `MENU_EQUIPMENT_START_KEY`, `MENU_EQUIPMENT_CAPTURE_KEY`, `CHANNEL_KEY_PREFIX+id`) maps to text that `message_router`'s own trigger-word sets (`GENERAL_HELP_WORDS`, watermark `TRIGGER_WORDS`, `EQUIPMENT_START_WORDS`, `EQUIPMENT_CAPTURE_WORDS`) actually recognize — cross-checked word-for-word, no mismatch. |
| `route_message` decision -> `.handle()` dispatch | `message_router.py`'s ~20 `"kind"` values (see its own catalogue doc-comment) | `.handle()`'s `if action["kind"] == ...` chain | Every kind the router can emit has a matching branch in `.handle()`; no kind is silently dropped. Field names each kind carries (`category`/`equipment`/`path`/`channel_id`/`stage`/`is_first_join`) match exactly what each consuming branch reads via `action[...]`. |
| Equipment stage persistence -> router input | `EquipmentSelectionTracker.get/start/set_category/set_pending_equipment/confirm/cancel` | `route_message`'s `equipment_stage` parameter, `.handle()`'s tracker calls | Every stage value the tracker can produce (`{}`, `awaiting_category`, `awaiting_equipment`, `awaiting_confirm`, `confirmed`) is handled by the router; `cancel()`'s `{}` output is the same Idle representation as never-started, confirmed consistent with the router's `stage = equipment_stage.get("stage")` (returns `None` for both). |
| `capture()` -> `_run_capture`/`_send_capture_reply` | `BrowserScreenshotService.capture()` return dict (`published_path`, `capture_ms`, ...) or raised exception | `wechat_image_reply.py`'s `_run_capture` | Success path reads `capture_info["published_path"]`/`capture_info.get("capture_ms", 0.0)` — both always present on success. Failure path (`except Exception`) is broad enough to catch every documented exception type (`KeyError`, `ValueError`, `FileNotFoundError`/`OSError`, `RuntimeError`) and converts it into a controlled `capture_error` result with a real placeholder image generated and sent. |
| `save_screenshot()` -> callers | `ScreenshotStore.save_screenshot(tab_name, image_bytes, duration_ms) -> ScreenshotRecord` | `BrowserScreenshotService.capture()` (2 call sites), `_store_incoming_image` (2 call sites: private + channel-filed) | All four call sites pass real `bytes` and a caller-composed multi-segment key (`{user_id}/channel_{id}/{original,watermarked}` or `{user_id}/channel_{id}` for incoming photos); none inspects `ScreenshotRecord` fields the store doesn't actually set. Dedup fix (`_dedupe_path`) is transparent to every caller — same return shape, only the on-disk filename can now carry a `-N` suffix. |
| `send_image_file`/`send_text` -> `.handle()` | `WeChatImageSender` return dicts (`media_id`, `upload_response`, `send_response`, `token_ms`, `upload_ms`, `send_ms`) or raised exception | `_send_capture_reply`, `_reply_text` | Every field `.handle()` reads via `send_info.get(...)` is present in the real sender's return dict; the exception path is now caught by `_send_capture_reply` (both call sites) and reported as `ok=False`/`send_error` without losing already-gathered `capture_info`/`trigger_kind` context. |

**No contract mismatch, incorrect result propagation, missing error propagation, wrong
parameter translation, or incorrect state transition between modules was found.** The three
prior sessions' fixes (cancel-from-any-stage, non-digit-input handling, `equipment_selected`
carrying `category`, the placeholder-image send bug, the filename dedup bug, the bare
`KeyError` on a malformed upload response, and the unguarded `send_image_file` calls) were each
already the correct fix at the seam they touched — re-verified here, not re-fixed.

## 4. Files Changed This Session

**None.** This was an audit/verification pass; no source file, test file, or script was
modified. The only new file is this handoff document, plus the `docs/TASK_STATUS.md` row
update described in Section 8.

## 5. Integration Bugs Fixed This Session

**None found.** All integration-level defects that existed in this codebase were already
identified and fixed by the three prior module sessions (see their own "Bugs Fixed" sections):

- Workflow MVP: cancel-from-any-active-stage, non-numeric-input handling during a pick,
  `equipment_selected` missing `category`, `cancel()`'s spurious `"none"` stage.
- Browser MVP: `_run_capture`'s exception branch never actually sending the placeholder image
  to the user (real silent-failure bug).
- Storage/Reply MVP: `ScreenshotStore` filename collisions silently overwriting a prior save,
  `WeChatImageSender` raising a bare `KeyError` on a malformed upload response, and both
  `send_image_file` call sites in `_run_capture` being unguarded against a sender exception.

This session's independent re-audit of every seam in Section 3 confirms all of the above are
still correctly wired together and none of them conflict with each other now that all three
change sets coexist in the same working tree.

## 6. Commands Executed

| Command | Result |
|---|---|
| `PYTHONPATH="$PWD/src" python -m pytest tests -v` | **110 passed, 7 subtests passed, 0 failed** |
| `PYTHONPATH="$PWD/src" python -m pytest tests/storage tests/wechat tests/workflow/test_reply_failure_boundary.py -v` | **20 passed** (targeted re-run of the storage-failure and sender-failure test coverage called out in the brief) |
| `PYTHONPATH="$PWD/src" python scripts/demo_mvp.py` | **Exit code 0**, no traceback; full transcript re-verified line by line (see Section 7) |

## 7. Validation Results

### Passed

- **Full automated test suite**: 110 tests / 7 subtests, all passing, covering
  `message_router`/`equipment_catalog`/`equipment_selection_tracker`/`user_team_tracker`
  (workflow), `screenshot_service`/`equipment_navigation`/capture-failure-containment
  (browser), `ScreenshotStore`/`WeChatImageSender`/reply-failure-boundary (storage/reply).
- **Successful capture (plain channel)**: demo Step 1 (`'1'` -> join + capture) and Step 6
  (equipment capture) both produced `ok=True`, `trigger_kind=browser_target`, a real
  `ScreenshotStore`-backed file, and a "sent" image line.
- **Browser failure**: demo Edge 5b (`browser.force_failure = True`) produced `ok=True`,
  `trigger_kind=capture_error`, a real placeholder image generated *and sent* (confirming the
  Browser MVP session's bug fix is intact) — plus 2 dedicated unit tests
  (`test_capture_failure_containment.py`) covering multiple exception types.
- **Storage failure**: not exercised by `demo_mvp.py` itself (`DemoBrowser`'s `ScreenshotStore`
  calls never fail in the scripted demo), but covered by `tests/storage/test_store.py`
  (write-permission failure via `unittest.mock.patch.object(Path, "write_bytes", ...)`,
  propagates cleanly, no partial file left) and
  `tests/workflow/test_reply_failure_boundary.py::test_storage_layer_failure_surfacing_through_capture_is_still_contained`
  (a `PermissionError` surfacing through `capture()` is still folded into a clean
  `capture_error` result with the placeholder image still sent). Both re-run this session,
  both pass.
- **Sender failure**: not exercised by `demo_mvp.py` (`DemoSender` never raises), but covered
  by `tests/wechat/test_image_sender.py` (8 tests: upload failure, send failure, missing
  `touser`, missing file, invalid `media_id`, access-token retry) and
  `tests/workflow/test_reply_failure_boundary.py`'s other 2 tests (a send failure after a
  successful capture, and a double failure where both capture *and* the placeholder-image
  send fail) — both confirm `.handle()` never raises and reports a truthful `ok=False`/
  `send_error` instead. Re-run this session, all pass.
- **Selection flow**: demo Steps 2-5 (category list -> pick -> confirm) plus Edge 1a/1b
  (second user, out-of-range digit re-prompt) plus the 40+12 dedicated
  `test_message_router.py`/`test_equipment_selection_tracker.py` tests covering every stage
  transition and edge case in the brief (no/one/many candidates, illegal index, cancel from
  every stage, duplicate confirm, lost/malformed state).
- **Channel flow**: demo Step 1 (join channel 1) and Edge 5a (join channel 2) — plain
  non-equipment channel join + capture path still works unmodified alongside the equipment
  flow, confirmed both by the demo and `test_message_router.py`'s
  `NonEquipmentRoutingStillWorksTests`.

### Blocked (live environment)

- **Live WeChat round trip** (real `api.weixin.qq.com` upload/send) — needs real
  `WECHAT_APPID`/`WECHAT_APPSECRET`/`WECHAT_OFFICIAL_WEBHOOK_TOKEN` and explicit authorization
  to contact the live API. Same standing gap as `docs/TASK_STATUS.md` Task 9.
- **Live Chrome/CDP/WebStation capture** (real Chrome, real login, real
  `10.121.0.14` dashboard) — needs network reachability to that internal-only IP, real
  `WEBSTATION_USERNAME`/`WEBSTATION_PASSWORD`, and explicit authorization. Same standing gap as
  `docs/TASK_STATUS.md` Task 8/10.
- **Real production storage-directory failure** (actual disk-full/ACL-denied on a deployed
  host) — only simulated via `unittest.mock.patch` in tests; no real failure condition was
  reproduced on any host.

### Not Run

- Ruff/lint, CI wiring — explicitly out of scope per this session's brief ("Do NOT... create
  CI, add Ruff").
- Any change to `win11-bot-01/02/03` — explicitly out of scope ("Do NOT... perform live
  testing"); no host was touched.

## 8. Known Limitations (carried forward, none new)

1. No state-expiry mechanism for the equipment-selection flow (Workflow MVP, deliberate,
   pending a product decision).
2. Duplicate-confirm has no dedicated reply text (Workflow MVP, deliberate, pending a product
   decision).
3. "Equipment page not found" vs. "slow render" are indistinguishable (Browser MVP, deliberate,
   pinned by a test).
4. `timeout_seconds` is shared between equipment-navigation wait and the screenshot call itself
   (Browser MVP, documented, not a bug).
5. No retry beyond the existing single `AccessTokenInvalidError`-triggered retry for a
   transient WeChat send failure (Storage/Reply MVP, deliberate, pending a product decision).
6. `device-agent-mvp/` remains an unrelated, disconnected prototype with an exposed API key in
   its `.env` — unchanged by this session, still needs the user's explicit rotation/removal
   decision (`docs/PROJECT_SNAPSHOT.md` Known Issues #4, `docs/TASK_STATUS.md` Task 13).
7. `docs/screenshot_store/README.md` still documents a stale key convention — unchanged by
   this session (out of scope: doc-only fix, not an integration defect); flagged previously in
   `docs/PROJECT_SNAPSHOT.md` Known Issues #2.

None of these are integration defects — each is either an already-flagged product-scope
question or a documented, deliberate boundary within a single module's own contract.

## 9. Real vs. Mock Boundary (project-wide summary)

- **Real, exercised for real, end to end**: `message_router.route_message` (pure logic),
  `EquipmentSelectionTracker`/`UserTeamTracker` (real JSON persistence), `equipment_catalog`
  (real CSV reads against the real 676-row production-scraped file), `ScreenshotStore` (real
  filesystem writes), `WatermarkRenderer` (real Pillow rendering in `scripts/demo_mvp.py`'s own
  config; disabled only inside the browser test suite's temp-config to avoid a system-font
  dependency), `WeChatImageReplyWorkflow.handle()` itself (the exact function the live webhook
  calls, never mocked anywhere), `WeChatWebhookServer`'s outer exception containment (read,
  confirmed, not modified).
- **Mock/fake, by necessity (no live credentials/network authorized this session)**: the
  Chrome/CDP layer (`CdpMultiTabService`/`BrowserProfileManager`, faked in `tests/browser/`;
  `DemoBrowser` in `scripts/demo_mvp.py`) and the WeChat HTTP layer
  (`WeChatOfficialClient`, faked via `client=` in `tests/wechat/`; `DemoSender` in
  `scripts/demo_mvp.py`).

This is the same boundary every prior handoff in this repo has drawn and documented
(`docs/MVP_DEMO.md` "Level C"); this session did not attempt to cross it, per the brief's
explicit "do NOT perform live testing" instruction.

## 10. Can QA Begin?

**Yes, for everything within the Level C (local, mocked-boundary) scope**: the full
execution chain from an incoming message to a WeChat reply — including channel join, the
select-equipment guided flow, plain-channel and equipment-path capture, storage, and every
documented failure mode (browser/CDP failure, storage failure, sender failure) — is verified
consistent end-to-end, has 110 passing automated tests, and a working repeatable local demo.
A QA pass focused on *routing/state-machine correctness, storage layout, and failure-message
correctness* can start immediately against `scripts/demo_mvp.py` and `tests/`.

**Not yet, for anything requiring a live environment**: real WeChat delivery and real
Chrome/CDP/WebStation capture remain blocked exactly as `docs/TASK_STATUS.md` Tasks 8/9/10
already record — that requires real credentials, network reachability to `10.121.0.14`, and
explicit user authorization to contact live external services, none of which this session has
or should assume.

## 11. Next Step

1. **User decision on committing**: per the project's standing working agreement (referenced
   in `docs/PROJECT_SNAPSHOT.md`, `docs/DEBUG_HANDOFF.md`, and every prior MVP handoff), none
   of the accumulated uncommitted work (module fixes, tests, docs) should be committed without
   the user explicitly asking. This session made no commits.
2. **Product decisions still open** (unchanged by this session, all deliberately left to the
   project owner rather than decided unilaterally by an agent): duplicate-confirm UX, state
   expiry, transient-send-failure retry policy — see Section 8.
3. **Live-environment verification** (`docs/TASK_STATUS.md` Task 8/9/10) remains the single
   biggest remaining gap before this MVP can be called fully done — needs real WeChat
   credentials, real network reachability to the WebStation dashboard, and explicit
   authorization, in a future session scoped for that.
4. **`device-agent-mvp/`'s exposed API key** (`docs/TASK_STATUS.md` Task 13) is still
   unresolved and still needs the user's direct attention — flagged again here since it sits
   in the same working tree as this MVP's code.
