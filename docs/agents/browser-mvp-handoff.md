# Browser MVP Handoff

- Task: Browser MVP -- stabilize the browser navigation/screenshot layer's public capture
  contract (see `docs/TASK_STATUS.md`)
- Owner: Browser Agent
- Date: 2026-07-20
- Status at handoff: contract documented, one real bug fixed, new test suite added and
  passing, `scripts/demo_mvp.py` re-verified; not committed, not merged, no live-environment
  (real Chrome/CDP/WebStation) verification

## Environment note (read this before trusting any file path below)

This session was launched from an isolated git worktree
(`.claude/worktrees/browser-capture-contract-718b36`, branch
`claude/browser-capture-contract-718b36`, based on commit `cbcc8ce`). That worktree has none of
`equipment_navigation.py`, `docs/PROJECT_RULES.md`/`PROJECT_SNAPSHOT.md`/`TASK_STATUS.md`, or
`tests/` -- confirmed directly (`ls` against both trees) before doing any work. They only exist
as **uncommitted changes in the main working tree**
(`C:\Users\frank\screenshot-bot-modular`, branch `feature/user-scoped-storage-and-channels`, tip
`cbcc8ce` + prior modified/untracked files). This matches exactly what
`docs/agents/mvp-integration-handoff.md` and `docs/agents/workflow-mvp-handoff.md` (prior
sessions, same date) already recorded about their own sessions. **All reading and editing for
this task was done in that main working tree**; nothing in the isolated
`browser-capture-contract-718b36` worktree was touched.

## Goal

Per the brief: produce one stable browser capture contract that accepts the equipment or
channel target the workflow needs and returns a result the storage/reply layer can consume --
document it, verify the required success/failure paths, ensure failures are controlled (never
crash the webhook, never silently report success with no real screenshot), and add minimal
tests, without inventing a new abstraction or touching out-of-scope modules.

## Current Browser Capture Contract

The public entrypoint is unchanged: `BrowserScreenshotService(config_path).capture(team_id,
tab=None, user_id=None, output_dir=None, image_name=None, timeout_seconds=15,
equipment_path=None, equipment_pane_height="12%", equipment_settle_seconds=3.0)` --
`src/screenshot_bot/browser/screenshot_service.py:80`. This audit found the existing contract
already meets the MVP; **no new abstraction was introduced**.

### Input
- `team_id`: str/int key into `browser_targets.targets` (config). Unconfigured -> `KeyError`
  from `BrowserTargetConfig.get_target` (`target_config.py:34`), raised before anything else
  runs (no Chrome/tab touched).
- `tab`: optional explicit tab index override; defaults to the target's own configured `"tab"`
  (default `0`). Out of range for the target's `tab_count` -> `ValueError` from
  `BrowserProfileManager.ensure_tab` (`profile_manager.py:55`).
- `user_id`: optional; falls back to `"unknown"` for storage filing if omitted.
- `output_dir`/`image_name`: optional; caller (`wechat_image_reply.py`) always passes both
  explicitly in production.
- `timeout_seconds`: shared by the CDP screenshot call **and** (when `equipment_path` is given)
  passed straight through as `navigate_equipment`'s own `timeout_seconds` -- there is no
  separate budget for "wait for the equipment graphic to render" vs. "wait for the screenshot
  itself"; both share whatever the caller passes (workflow default: 15s, see
  `capture_timeout_seconds` in `wechat_official_webhook` config).
- `equipment_path`: optional. **Falsy values (`None`, `""`) silently skip equipment navigation
  entirely** and fall back to a plain channel capture -- documented, not a bug (see
  `screenshot_service.py:107`, `if equipment_path:`). A non-empty but non-existent/malformed
  path is indistinguishable from a slow-to-render one (see "Equipment page not found /
  malformed path" below).

### Output (success)
A dict (no `"ok"` field of its own -- the caller decides what "ok" means; see "Failure
representation" below): `source`, `team_id`, `target_name`, `tab`, `user_id`,
`equipment_path`, `debug_port`, `browser_startup`, `page_title`, `page_url`, `raw_path`,
`published_path` (watermarked, for the WeChat reply), `store_path` (pre-watermark audit copy),
`watermarked_store_path` (post-watermark audit copy), `capture_ms`, `watermark_ms`, plus
watermark metadata (`watermark_applied`, `watermarked_path`). Fully documented already in
`src/screenshot_bot/browser/README.md`.

### Failure representation
`capture()` raises; it never returns a "failed" result dict. Exception types seen across the
full call chain, all of them plain, undecorated stdlib exceptions:
- `KeyError` -- target not configured (`target_config.py`)
- `ValueError` -- tab index out of range for the target's `tab_count` (`profile_manager.py`)
- `FileNotFoundError` (an `OSError`) -- Chrome executable not found (`cdp_multi_tab_service.py`,
  `resolve_chrome_path`)
- `RuntimeError` -- the large majority of failures: Chrome never opened its debug port
  (`wait_for_port`), a tab isn't debuggable (`_get_page`), a login form never became ready /
  fields not found / submit button not found (`login`), a `keep_alive` ping reports the session
  logged out, the equipment graphic never rendered svg content within the timeout
  (`navigate_to_equipment_graphic`)
- Lower-level `OSError`/socket errors from `urllib`/raw sockets (`devtools_client.py`) when
  Chrome itself is unreachable

**The workflow layer is what turns this into a controlled result**, not `capture()` itself:
`WeChatImageReplyWorkflow._run_capture` (`wechat_image_reply.py:269`) wraps the
`self.browser.capture(...)` call in `except Exception as exc:` -- broad enough to catch every
exception type above -- and converts it into `{"ok": True, "trigger_kind": "capture_error",
"capture_error": str(exc), ...}` plus (after this session's fix, see "Bugs Fixed") an actual
placeholder image generated and sent to the user. One layer further out,
`WeChatWebhookServer` (`wechat/webhook_server.py:119-122`) already wraps the entire
`message_processor.handle(...)` call in its own `except Exception`, so even a hypothetical
exception this session didn't anticipate cannot crash the webhook process -- confirmed by
reading, not modified.

### Timeout behavior
`timeout_seconds` (capture()'s param, default 15) governs both the CDP `screenshot()` call and,
when applicable, `navigate_equipment`'s render-wait -- see "Input" above. `equipment_navigation
.navigate_to_equipment_graphic`'s own default (`timeout_seconds=35`) is never actually used in
the production call path, since `screenshot_service.py:114` always passes the capture's own
`timeout_seconds` explicitly.

### Browser connection behavior
`BrowserProfileManager.ensure_tab` (`profile_manager.py:53`) checks whether the configured debug
port is already open; if not, launches Chrome and blocks (`wait_for_port`, raising `RuntimeError`
on timeout) until it is. Tab creation/adoption follows -- `adopt_tab` first (matches an
already-open tab by URL origin, so a process restart doesn't open a duplicate/re-attempt a login
a login-gated site would reject), `add_tab` otherwise. All of this is serialized by one
process-local `threading.Lock` (`profile_manager.py:48`) so a concurrent `warm_up()`/request pair
can't race during provisioning; screenshotting an already-established tab is not serialized here
(only provisioning is).

### Login/session behavior
First `ensure_tab()` call for a target's tab 0 triggers `_apply_login` if `login.enabled` --
failure (missing env var, form fields not found, timeout) raises and is **not** cached as
"handled", so the very next `capture()`/`warm_up()` call retries login rather than getting stuck.
`keep_alive`/auto-`refresh` run on independent background threads per tab
(`cdp_multi_tab_service.py:338,406`), each with a per-tab `threading.Lock` (`_lock_for`) so a
scheduled refresh can't tear down a page mid-login/mid-ping. A `keep_alive` failure triggers a
`_recover` closure (`profile_manager.py:130`) that re-navigates and re-logs-in automatically --
none of this touches `capture()`'s own exception surface; it's entirely a background concern.

## Bugs Fixed

**One real bug, found via the new `test_capture_failure_containment.py` test** (initially
written to *confirm* documented behavior; it instead caught documented behavior being false):

- `WeChatImageReplyWorkflow._run_capture`'s exception branch
  (`src/screenshot_bot/workflow/wechat_image_reply.py`, in the `except Exception as exc:` block)
  generated a local placeholder image via `write_latency_image` and set
  `result["ok"] = True, trigger_kind = "capture_error"` -- but **never called
  `self.image_sender.send_image_file(...)`**. A real browser/CDP failure in production would
  silently leave the WeChat sender with **no reply at all** (no text, no image), while the
  webhook's own log/JSONL line recorded `ok=True`. This directly contradicts
  `docs/MVP_DEMO.md`'s and `docs/agents/mvp-integration-handoff.md`'s description of this path
  ("an error-placeholder image is still generated and 'sent'") -- that claim was based on
  `scripts/demo_mvp.py`'s `send()` helper, which only prints `ok`/`trigger_kind` and never
  checked whether `DemoSender.sent` actually grew, so the gap went unnoticed in that session.
  **Fix**: the exception branch now also calls `self.image_sender.send_image_file(touser,
  str(image_path))` and folds its response (`media_id`, `upload_response`, `send_response`,
  `token_ms`, `upload_ms`, `send_ms`, `total_latency`) into the result, mirroring the success
  path's shape so log analysis doesn't need a different schema per outcome. Re-ran
  `scripts/demo_mvp.py` after the fix: Edge 5b (simulated browser failure) now shows a
  `[WeChat -> demo-user-006] <image> ...` line that was silently absent before.
  - Risk introduced: `send_image_file` itself can now raise inside this branch (e.g. a WeChat
    API failure on top of a browser failure). This is not a new class of risk -- the success
    path already calls `send_image_file` unguarded a few lines below with the same exposure --
    and it's still caught by `WeChatWebhookServer`'s outer `except Exception` either way, so the
    webhook process still cannot crash from it.

No other bugs were found in `screenshot_service.py`, `equipment_navigation.py`,
`profile_manager.py`, or `cdp_multi_tab_service.py` themselves -- the Chrome/CDP layer's failure
containment (raise cleanly, never silently swallow, never mark a failed login as handled) was
already correct on inspection and is now pinned by the new tests below.

## Known Limitation (documented, not fixed)

**"Equipment page not found" and "malformed equipment path" are indistinguishable from a slow
render.** `equipment_navigation.navigate_to_equipment_graphic` has no signal for "this hash
route doesn't correspond to any real equipment" separate from "the graphic is just slow to
render" -- both manifest as the identical `RuntimeError: timed out waiting for equipment graphic
content: <path>` after the same timeout. Per the brief ("do not invent a new abstraction unless
the current interface cannot meet the MVP"), this was left as-is: the failure is still clean,
still raised, still converted into a controlled `capture_error` result by the workflow layer --
it just carries less diagnostic precision than a dedicated "not found" signal would. Pinned by
`test_equipment_page_not_found_surfaces_as_the_same_navigation_timeout` in
`tests/browser/test_screenshot_service.py` so a future session that *does* want to distinguish
these has a concrete test to change.

## Files Changed

- `src/screenshot_bot/workflow/wechat_image_reply.py` -- the one bug fix above (`_run_capture`'s
  exception branch now sends the placeholder image). This is the "minimal consumer adjustment"
  the brief allows; everything else in that file (capture/storage/send orchestration, the
  equipment-flow branches from the prior Workflow Agent session) was read but not touched.
- `tests/browser/_fakes.py` (new) -- shared fakes: `FakeCdpService` (stands in for
  `CdpMultiTabService`'s `screenshot`/`navigate_equipment`/`list_tabs`), `FakeProfileManager`
  (stands in for `BrowserProfileManager`, configurable to raise on `ensure_tab`), and
  `build_service()` (constructs a real `BrowserScreenshotService` against a temp config, with
  only `profile_manager` swapped for a fake -- everything else, including `ScreenshotStore` and
  `WatermarkRenderer`, runs for real against a temp directory).
- `tests/browser/test_screenshot_service.py` (new) -- `capture()` contract tests.
- `tests/browser/test_equipment_navigation.py` (new) -- pure tests for
  `navigate_to_equipment_graphic` (success, timeout, safe path escaping) using a fake DevTools
  client, no real websocket.
- `tests/browser/test_capture_failure_containment.py` (new) -- the consumer-boundary test that
  found the bug above; drives the real `WeChatImageReplyWorkflow.handle()` with a fake browser
  whose `.capture()` raises, asserting the exception never propagates and a controlled result
  comes back instead.

No changes to `message_router.py`, `equipment_catalog.py`, `equipment_selection_tracker.py`,
`equipment_prompts.py`, `user_team_tracker.py`, `ScreenshotStore` internals, or
`WeChatImageSender` internals -- confirmed via `git status --short` scoped to those paths before
finishing, per the brief's module-boundary requirement.

## Tests Added

`tests/browser/` -- 18 tests (unittest-style, `pytest`-run, matching `tests/workflow/`'s
existing convention: no `__init__.py`, plain `TestCase` classes):

| File | Covers |
|---|---|
| `test_screenshot_service.py` | successful channel capture; successful equipment-path capture; falsy equipment_path degrades to plain capture (documented, not a bug); CDP connection unavailable; browser process unavailable; target tab unavailable; login/session failure; equipment navigation timeout; equipment-not-found (same timeout, documented limitation); screenshot generation failure; unconfigured target (KeyError); malformed tab index (ValueError) -- 11 tests, all asserting no partial `ScreenshotStore` write happens on any failure path |
| `test_equipment_navigation.py` | successful navigate + resize; timeout when svg never renders; a path with quotes/backslashes is safely `json.dumps`-escaped (no JS injection); an empty-string path run directly still executes the normal sequence (the falsy short-circuit lives one layer up, in `capture()`) -- 4 tests |
| `test_capture_failure_containment.py` | a `browser.capture()` exception becomes a controlled `ok=True`/`trigger_kind="capture_error"` result with an actual image sent, never an uncaught exception; three different exception types (`FileNotFoundError`, `KeyError`, `ValueError`) are all contained the same way -- 2 tests (one with 3 subtests) |

None of these require a real Chrome process, the internal BMS network, live credentials, or
WeChat -- the Chrome/CDP boundary is fully faked; `ScreenshotStore` and `WatermarkRenderer` run
for real against temp directories (watermarking is disabled in the test config to avoid
depending on system fonts).

## Commands Executed

| Command | Result |
|---|---|
| `PYTHONPATH="$PWD/src" python -m pytest tests/browser -v` | **Passed** -- 18 passed, 3 subtests passed |
| `PYTHONPATH="$PWD/src" python -m pytest tests -v` (full suite: `tests/browser/` + prior session's `tests/workflow/`) | **Passed** -- 90 passed, 7 subtests passed, 0 failed |
| `PYTHONPATH="$PWD/src" python scripts/demo_mvp.py` | **Passed** -- exit code 0, no traceback; re-verified the Edge 5b (simulated browser failure) transcript now shows the image actually being sent, confirming the bug fix |
| Live CDP validation (real Chrome, real WebStation at `10.121.0.14`) | **Not Run** -- no network reachability, no `WEBSTATION_USERNAME`/`WEBSTATION_PASSWORD` credentials, no authorization to contact the real dashboard from this session; matches every prior handoff's standing limitation (`docs/TASK_STATUS.md` Task 8/10) |

## Real vs Mock Validation Boundary

- **Real**: `BrowserTargetConfig` (target parsing), `ScreenshotStore` (file writes verified on
  disk), `WatermarkRenderer` (real Pillow render, watermark disabled in test config only to
  avoid a system-font dependency -- exercised for real, unmocked, in `scripts/demo_mvp.py`'s own
  run since that config doesn't disable it), `equipment_navigation.navigate_to_equipment_graphic`
  (real function under test, fake client), `WeChatImageReplyWorkflow._run_capture`/`.handle()`
  (real, unmocked).
- **Mock**: `CdpMultiTabService` (`FakeCdpService`) and `BrowserProfileManager`
  (`FakeProfileManager`) -- i.e. everything that would otherwise touch a real Chrome process,
  a real websocket, or a real login-gated site. This is the same boundary every prior handoff in
  this repo has drawn (`scripts/demo_mvp.py`'s `DemoBrowser`, `docs/MVP_DEMO.md` "Level C") --
  this session did not attempt to cross it.

## Known Limitations

1. Equipment-not-found vs. slow-render indistinguishability (see above) -- deliberate, not
   fixed, pinned by a test.
2. `timeout_seconds` is shared between the equipment-navigation wait and the screenshot call
   itself (see "Timeout behavior") -- not a bug, but worth knowing if equipment graphics turn
   out to need meaningfully longer than plain screenshots.
3. No live Chrome/CDP/WebStation verification this session (see "Commands Executed") -- same
   standing gap as `docs/TASK_STATUS.md` Task 8/10.
4. The newly-fixed `send_image_file` call in `_run_capture`'s exception branch is itself
   unguarded (matching the success path) -- if the WeChat API is *also* down when a capture
   fails, that raises out of `_run_capture`/`.handle()`, caught only by the outer
   `WeChatWebhookServer` try/except (still contained, still can't crash the process, but the
   webhook's per-message log line for that request would record the exception there instead of
   a clean `capture_error` result). Not fixed here -- it mirrors pre-existing, unflagged behavior
   in the success path rather than being a regression this session introduced, and papering over
   it would mean guessing at desired UX for a double-failure case with no product guidance.

## Did Any Public Interface Change?

**No.** `BrowserScreenshotService.capture()`'s signature, return shape, and exception surface
are all unchanged. The one code change (`wechat_image_reply.py`'s `_run_capture`) is
consumer-side only -- it changes what the *workflow* does with a capture failure (send the
placeholder it already generates) and adds fields to `_run_capture`'s own internal `result`
dict; it does not touch `capture()` or any other browser-module public API.

## Is Integration Agent Action Required?

No new integration work is required -- the contract this documents is exactly what
`docs/agents/mvp-integration-handoff.md` already audited and wired through
`WeChatImageReplyWorkflow.handle()`. The one behavior change (capture failures now actually send
a reply) is strictly additive from the Integration Agent's perspective: `scripts/demo_mvp.py`
needed no changes and its transcript for every other scenario is byte-for-byte unchanged: only
Edge 5b's previously-silent gap in `DemoSender.sent` is now filled. Worth a note if
`docs/MVP_DEMO.md` is revised later, since its current wording ("an error-placeholder image is
still generated and 'sent'") was aspirational until this fix, not previously accurate.

## Next Step

1. Get the project owner's decision on whether the double-failure case (browser fails *and*
   the WeChat send of the placeholder also fails) deserves a dedicated result shape, or whether
   falling through to the outer webhook-level exception handler is acceptable -- this session
   left it as-is (see "Known Limitations" #4) rather than deciding unilaterally.
2. This mirrors every prior handoff's standing note: **do not commit** any of this without the
   user explicitly asking (per the project's working agreement referenced in
   `docs/PROJECT_SNAPSHOT.md`).
3. Live Chrome/CDP/WebStation verification remains open (`docs/TASK_STATUS.md` Task 8/10) --
   unchanged by this session, needs real credentials + network reachability + explicit
   authorization.
