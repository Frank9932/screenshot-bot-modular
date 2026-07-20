# Storage / Reply MVP Handoff

- Task: Storage / Reply MVP -- stabilize `screenshot_store/` (persistence) and
  `wechat/image_sender.py` (WeChat reply) for the final MVP segment: Screenshot result ->
  ScreenshotStore -> WeChat image reply (see `docs/TASK_STATUS.md`)
- Owner: Storage / Reply Agent
- Date: 2026-07-20
- Status at handoff: contracts documented, three real bugs fixed, new test suite added and
  passing, `scripts/demo_mvp.py` re-verified; not committed, not merged, no live-environment
  (real WeChat API) verification

## Goal

Per the brief: make storage and image-reply behavior reliable, independently testable, and
ready for project-level integration, without redesigning the architecture, without touching
`message_router.py`/`equipment_catalog.py`/`equipment_selection_tracker.py`/
`equipment_prompts.py`/`user_team_tracker.py`/`browser/screenshot_service.py`/
`browser/equipment_navigation.py`, and with only a minimal, documented change to
`wechat_image_reply.py` if needed to correctly handle storage or sender results.

## Current Storage Contract (`screenshot_store/store.py`)

Unchanged public surface: `ScreenshotStore(base_dir="storage/screenshots")`,
`ScreenshotStore.save_screenshot(tab_name: str, image_bytes: bytes, duration_ms: int) ->
ScreenshotRecord`. `ScreenshotRecord` is a frozen dataclass (`tab_name`, `file_path`,
`created_at`, `duration_ms`, `size_bytes`) -- an in-memory return value only, never itself
persisted to disk.

- **Input**: `tab_name` is an arbitrary caller-chosen relative path segment, not necessarily a
  literal "tab" -- despite the parameter name, callers pass multi-segment keys like
  `"{user_id}/channel_{team_id}/original"` (`browser/screenshot_service.py:129-131,154-156`) or
  `"{user_id}/channel_{id}"` (`workflow/wechat_image_reply.py:412-413`). `image_bytes` must be a
  real `bytes`-like object; `duration_ms` is embedded directly into the filename.
- **Returned value**: a `ScreenshotRecord` with the real on-disk `file_path`, wall-clock
  `created_at`, the caller's `duration_ms`, and `size_bytes` computed from the actual bytes
  written (not the input length blindly trusted, though in practice they're the same value).
- **Generated path / directory layout**: `{base_dir}/{tab_name}/{YYYYMMDD_HHMMSS_mmm}_{duration_ms}ms.png`
  (now with an optional `-N` de-dup suffix, see "Bugs Fixed"). `base_dir` is fixed at
  construction; every `tab_name` segment becomes a real nested directory.
- **User/channel isolation**: enforced entirely by whatever key the *caller* composes -- the
  store itself has no notion of "user" or "channel," it's just `pathlib` joining segments. Two
  different `tab_name` keys can never collide on disk (confirmed by test); isolation is a
  property of the caller's key convention, not the store.
- **Duplicate filename behavior (bug, now fixed)**: see "Bugs Fixed" below.
- **Metadata behavior**: **there is none**. No sidecar JSON/metadata file is ever written --
  `ScreenshotRecord` is the only descriptor, and it lives only in the caller's Python process.
  Confirmed via a new pinning test (`test_no_metadata_sidecar_file_is_written`) so a future
  change to add metadata persistence is a deliberate decision, not an accidental gap.
- **Failure behavior**: `save_screenshot` does not catch anything. `tab_dir.mkdir(parents=True,
  exist_ok=True)` already handles "missing destination directory" transparently (creates
  arbitrarily deep paths, no error if it already exists). A write failure (permission denied,
  disk full, invalid `image_bytes` type) raises the underlying `PermissionError`/`OSError`/
  `TypeError` straight out to the caller -- there is no partial/corrupt `ScreenshotRecord`
  returned on failure, and (per the new test) no stray file left in the target directory when
  the write itself fails.
- **Cleanup behavior**: none exists in this module (nothing to verify/preserve here).

## Current Sender Contract (`wechat/image_sender.py`)

Unchanged public surface: `WeChatImageSender(appid, appsecret, client=None)`,
`.send_image_file(touser, image_path) -> dict`, `.send_text(touser, content) -> dict`.

- **Input**: `touser` (WeChat `openid`) and `image_path` (a local file path, string or
  path-like). Missing `touser` raises `RuntimeError` immediately, before touching the client.
- **Upload/send sequence**: `get_access_token()` (cached, `force_refresh` on demand) ->
  `upload_temporary_image(token, image_path)` -> `send_customer_image(token, touser, media_id)`.
  If the first attempt hits `AccessTokenInvalidError` (server rejected a token the cache thought
  was still valid), the whole sequence retries exactly once with `force_refresh=True` -- this is
  unchanged, already-correct behavior, confirmed by test.
- **Success representation**: `{"media_id", "upload_response", "send_response", "token_ms",
  "upload_ms", "send_ms"}`. `media_id` is only ever a non-empty string on a genuine success path,
  now enforced defensively (see "Bugs Fixed").
- **Upload failure behavior**: the real `WeChatOfficialClient.upload_temporary_image` already
  raises `RuntimeError` for any non-zero `errcode` or a missing `media_id` in the response
  (`official_api.py:64-65`) -- `send_image_file` does not catch this (other than the one
  specific `AccessTokenInvalidError` retry), so it propagates to the caller. `send_customer_image`
  is never called if upload failed (confirmed by test).
- **Send failure behavior**: same shape -- `send_customer_image` raises `RuntimeError` for a
  non-zero `errcode`; propagates to the caller. Confirmed distinguishable from an upload failure
  (upload call count is 1, not 0, when only send fails).
- **Missing image file behavior**: `send_image_file`/`WeChatImageSender` do not stat the path
  themselves -- the real client's multipart encoder (`official_api.encode_multipart`) calls
  `Path(path).read_bytes()` directly, so a missing file surfaces as a clean `FileNotFoundError`
  before any HTTP request is made. Confirmed by a direct test of `encode_multipart`.
  `WeChatImageSender` has no path-existence pre-check of its own to add here -- the failure is
  already clean and already happens before any network call.
- **Invalid returned media identifier (bug, now fixed)**: see "Bugs Fixed" below.
- **Sender exception containment**: `send_image_file`/`send_text` never swallow a failure into a
  fake-success return value -- every failure path raises a plain exception. It is the *caller's*
  job to contain that (see "Files Changed" below for where that containment now correctly
  happens in the reply workflow).

## Bugs Fixed

1. **`ScreenshotStore` duplicate/repeated filename could silently overwrite a prior save.**
   The filename is `{timestamp-to-the-millisecond}_{duration_ms}ms.png` with no other
   uniqueness guarantee -- two saves to the *same* key within the same millisecond and with the
   same rounded `duration_ms` (a realistic trigger: two rapid re-sends/re-captures to the same
   `{user_id}/channel_{id}/original` folder) would resolve to the identical filename, and the
   second `write_bytes` would silently clobber the first with no error and no signal anywhere.
   **Fix** (`src/screenshot_bot/screenshot_store/store.py`): new `_dedupe_path()` helper --
   before writing, if the computed path already exists, append an incrementing `-1`, `-2`, ...
   suffix until a free name is found. No change to the base naming scheme or to the public API;
   this only ever changes behavior in the (previously silently-broken) collision case. Pinned by
   `test_duplicate_filename_does_not_overwrite_prior_save` and
   `test_dedupe_path_appends_incrementing_counter` in `tests/storage/test_store.py`.

2. **`WeChatImageSender._upload_and_send` indexed `upload["media_id"]` directly**, which crashes
   with a bare, undiagnosable `KeyError: 'media_id'` if the upload response is ever missing that
   key. The real `WeChatOfficialClient.upload_temporary_image` already guarantees this can't
   happen against the live API (it raises first) -- but this is exactly the kind of contract gap
   the brief asked to verify ("invalid returned media identifier"), and it was live and
   reachable against any other/future/fake client that doesn't share that same guarantee (this
   session's own first draft of `test_invalid_media_id_in_upload_response_...` caught it as
   soon as a client without that guarantee was used). **Fix**
   (`src/screenshot_bot/wechat/image_sender.py`): `_upload_and_send` now does
   `media_id = upload.get("media_id")` and raises a clear `RuntimeError("upload response missing
   media_id: ...")` *before* calling `send_customer_image`, rather than crashing partway through
   that call with an opaque `KeyError`, and rather than silently sending a customer-image message
   with no media_id. Pinned by
   `test_invalid_media_id_in_upload_response_raises_clean_error_not_a_bare_keyerror`.

3. **`WeChatImageReplyWorkflow._run_capture` called `send_image_file` unguarded on *both* its
   success path and its capture-error placeholder path.** A prior session (Browser Agent, see
   `docs/agents/browser-mvp-handoff.md`) had already fixed the placeholder path to actually call
   `send_image_file` at all -- but neither call was wrapped in a `try`/`except`. If the WeChat
   send itself failed (e.g. a real upload/send-stage `RuntimeError`, independent of whether
   capture succeeded), the exception propagated all the way out of `.handle()`, discarding every
   field already gathered in `result` (`screenshot_path`, `capture_ms`, `trigger_kind`,
   `capture_info`, etc.) and was only caught one layer further out by
   `WeChatWebhookServer._process_async`'s generic `except Exception`, which logs a *different*,
   much thinner shape (`{received_at, msg_type, touser, content, msg_id, dedupe_key, error,
   ok: False}`) with none of that stage context. This directly violated the brief's core
   requirement: "the system must not confuse browser capture success / local storage success /
   WeChat upload success / WeChat message-send success -- each stage must have a truthful
   result." A send failure *after* a genuinely successful capture was, in the log, indistinguishable
   from an XML-parse error or a webhook auth failure. **Fix**
   (`src/screenshot_bot/workflow/wechat_image_reply.py`): extracted a new `_send_capture_reply`
   helper that both call sites now go through; it wraps `send_image_file` in `try`/`except` and,
   on failure, sets `result["ok"] = False` and `result["send_error"] = str(exc)` while *preserving*
   every stage field already set (`trigger_kind`, `screenshot_path`, `capture_ms`,
   `capture_error` if applicable) -- so the returned result (still returned normally, never
   raised) truthfully distinguishes "capture/storage succeeded, send failed" from "capture itself
   failed" from any other failure shape, and `.handle()` never raises because of a sender
   exception either. Pinned by all three tests in
   `tests/workflow/test_reply_failure_boundary.py`.

No other bugs were found in `screenshot_store/models.py`, `wechat/official_api.py`'s upload/send
HTTP mechanics, or `wechat/webhook_server.py`'s outer exception handling (already correctly
catches and logs, confirmed by reading, not modified) -- confirmed on inspection and now pinned
by the new tests.

## Files Changed

- `src/screenshot_bot/screenshot_store/store.py` -- Bug 1 fix (`_dedupe_path` helper +
  `save_screenshot` using it). Public API (`ScreenshotStore(base_dir=...)`,
  `save_screenshot(tab_name, image_bytes, duration_ms) -> ScreenshotRecord`) unchanged.
- `src/screenshot_bot/wechat/image_sender.py` -- Bug 2 fix (`_upload_and_send`'s media_id guard).
  Public API (`WeChatImageSender(appid, appsecret, client=None)`, `.send_image_file`,
  `.send_text`) and return-dict shape unchanged.
- `src/screenshot_bot/workflow/wechat_image_reply.py` -- Bug 3 fix: the one "minimal change...
  allowed only if necessary to correctly handle storage or sender results" the brief permits.
  `_run_capture`'s two `send_image_file` call sites were replaced with calls to a new
  `_send_capture_reply(result, started, touser, image_path)` helper method on the same class;
  no other method, and no other file, was touched. `capture()`'s own contract
  (`BrowserScreenshotService`, documented in `docs/agents/browser-mvp-handoff.md`) is unaffected.
  Nothing in `message_router.py`, `equipment_catalog.py`, `equipment_selection_tracker.py`,
  `equipment_prompts.py`, `user_team_tracker.py`, `browser/screenshot_service.py`, or
  `browser/equipment_navigation.py` was touched -- confirmed via `git status --short` scoped to
  those paths before finishing.

## Tests Added

- `tests/storage/test_store.py` (new, 9 tests) -- successful save; automatic directory creation
  for a brand-new multi-segment key; duplicate-filename collision no longer overwrites (forces
  the collision deterministically by patching `datetime.now`); the `_dedupe_path` helper's
  counter behavior directly; invalid source (`None` instead of `bytes`) raises `TypeError`
  rather than writing garbage; write-permission failure (`PermissionError` via
  `unittest.mock.patch.object(Path, "write_bytes", ...)`) propagates and leaves no partial file
  behind; user/channel path isolation across three different keys; the filename-building helper
  directly; confirms no metadata sidecar file exists.
- `tests/wechat/test_image_sender.py` (new, 8 tests) -- successful upload+send with a fake
  client (`client=` constructor param, no real network); upload failure propagates and never
  reaches send; send failure after a successful upload propagates (and is distinguishable --
  upload call count is 1); missing `touser` raises before touching the client; missing image
  file raises `FileNotFoundError` from the real `encode_multipart` before any HTTP call; invalid/
  missing media_id in the upload response now raises a clear `RuntimeError` (Bug 2, was a bare
  `KeyError`) and never reaches `send_customer_image`; access-token-invalid triggers exactly one
  retry with a forced refresh; a generic sender failure is confirmed to be a plain raised
  exception, never a fake-success return value.
- `tests/workflow/test_reply_failure_boundary.py` (new, 3 tests -- the required
  workflow-boundary test, extended to 3 scenarios) -- drives the real
  `WeChatImageReplyWorkflow.handle()` (the exact function the live webhook calls) with a fake
  browser and a fake sender configured to fail:
  1. Capture succeeds, then the WeChat send itself fails -- `.handle()` must not raise; result
     must be `ok=False` with a `send_error`, while still truthfully reporting
     `trigger_kind="browser_target"` and the real `screenshot_path` (proves stage-success
     information survives a later stage's failure).
  2. Capture *and* the placeholder-image send both fail (double failure) -- `.handle()` must
     still not raise; both `capture_error` and `send_error` must be present and distinguishable.
  3. A storage-layer failure type (`PermissionError`, representing `ScreenshotStore`'s own write
     failure bubbling up through the real, unguarded `self.store.save_screenshot()` call inside
     `BrowserScreenshotService.capture()`) is still contained by the existing `capture_error`
     path, with the placeholder image still genuinely sent.

None of these tests touch the real WeChat API, real network, real Chrome/CDP, or production
runtime directories -- everything runs against `tempfile.TemporaryDirectory()` and fake/stub
collaborators (`client=` for the sender, a fake `browser`/`image_sender` pair for the workflow
test), following the same style already established by `tests/browser/` and `tests/workflow/`.

## Commands Executed

| Command | Result |
|---|---|
| `$env:PYTHONPATH = "$PWD\src"; python -m pytest tests/storage -v` | **Passed** -- 9 passed |
| `$env:PYTHONPATH = "$PWD\src"; python -m pytest tests/wechat -v` | **Passed** -- 8 passed |
| `$env:PYTHONPATH = "$PWD\src"; python -m pytest tests -v` (full suite) | **Passed** -- 110 passed, 7 subtests passed, 0 failed (was 90 passed/7 subtests before this session's additions) |
| `$env:PYTHONPATH = "$PWD\src"; python scripts\demo_mvp.py` | **Passed** -- exit code 0, no traceback; transcript re-verified byte-for-byte equivalent in shape to the prior session's (same categories/items/edge-case replies; only filenames/timestamps differ run to run, as before) |
| Live WeChat API validation (real `upload_temporary_image`/`send_customer_image` against `api.weixin.qq.com`) | **Not Run** -- no live credentials, no authorization to contact the real WeChat API from this session |
| Live production storage-directory validation (real disk-full/real permission-denied on a deployed host) | **Not Run** -- simulated only, via `unittest.mock.patch` in `tests/storage/test_store.py`; no real disk-full/ACL-denied condition was reproduced on any host |

## Real vs Mock Boundary

- **Real, exercised for real**: `ScreenshotStore` (real filesystem writes to a temp directory,
  real `pathlib` behavior, real dedup logic), `WeChatImageReplyWorkflow.handle()`/`_run_capture`/
  `_send_capture_reply` (real, unmocked orchestration logic), `official_api.encode_multipart`
  (real multipart encoding, used directly in the missing-file test).
- **Mock/fake**: the WeChat HTTP layer itself (`WeChatOfficialClient` is never instantiated in
  the sender tests -- `WeChatImageSender(client=FakeClient())` is used throughout, so no request
  ever reaches `api.weixin.qq.com`), the browser/CDP layer in the workflow-boundary test (a
  `FakeBrowser` whose `.capture()` either raises a scripted exception or returns a canned
  `capture_info` dict pointing at a real temp PNG).

## Known Limitations

1. **No live WeChat API verification** -- matches every prior handoff's standing limitation
   (`docs/TASK_STATUS.md` Task 9, already `Blocked` before this session). The fixes and new
   tests in this session are all local/unit-level; the real `api.weixin.qq.com` endpoints were
   never contacted.
2. **The duplicate-filename fix changes on-disk behavior only in the previously-broken
   collision case** -- it does not add a metadata/index file, does not change the base naming
   convention, and does not attempt to make the filename globally unique by any means other than
   the new incrementing suffix (e.g. no UUID). This was a deliberate minimal fix per the brief's
   instruction not to invent new abstractions.
3. **`_send_capture_reply`'s failure branch does not attempt any retry of the WeChat send** -- a
   transient send failure (e.g. one flaky HTTP call) is reported as a clean `ok=False` and the
   message is genuinely not delivered to the user for that request. `WeChatImageSender` itself
   already retries once internally for the one specific `AccessTokenInvalidError` case (unchanged,
   pre-existing behavior); anything beyond that (e.g. general retry-with-backoff for transient
   network errors) is out of this session's scope -- not a documented requirement anywhere, and
   would be new product/reliability scope, not a bug fix.
4. **Storage-failure-during-capture is only tested indirectly** (a `PermissionError` raised by a
   fake `browser.capture()`, standing in for what `ScreenshotStore.save_screenshot()` would raise
   if the real, unguarded call inside `BrowserScreenshotService.capture()` hit a real disk/
   permission failure) -- this mirrors the existing, deliberate design where `capture()`'s own
   internals (including its two `ScreenshotStore` calls) are not separately try/excepted; the
   *workflow* layer is what turns any exception from `capture()` into a controlled result,
   regardless of which internal step actually failed. This is consistent with
   `docs/agents/browser-mvp-handoff.md`'s own documented failure-representation contract for
   `capture()`, not a gap introduced or left open by this session.

## Public Interface Changes

**None of the three fixes change any public function/method signature or return shape in the
success case.** Specifically:
- `ScreenshotStore.save_screenshot(tab_name, image_bytes, duration_ms) -> ScreenshotRecord` --
  same signature, same `ScreenshotRecord` fields; the only behavior change is that a filename
  collision now resolves to a new, still-valid path instead of overwriting.
- `WeChatImageSender.send_image_file(touser, image_path) -> dict` -- same signature, same
  success-dict shape; the only behavior change is that a specific malformed-response case now
  raises a clearer `RuntimeError` instead of an opaque `KeyError` (both are exceptions the
  caller must already have been prepared to handle; this only makes the message useful).
- `WeChatImageReplyWorkflow._run_capture(...)`'s **external** behavior (from `.handle()`'s
  perspective) is unchanged on every path this repo's existing tests already covered (confirmed
  by the full 110-test suite passing, including the pre-existing
  `tests/browser/test_capture_failure_containment.py`). The only *new* externally-observable
  behavior is the new `send_error`/`ok=False` result shape for a case (`send_image_file` itself
  raising) that previously was not a controlled result at all -- it's additive, not a breaking
  change to any previously-relied-upon field.

## Is Integration Agent Action Required?

**No new integration work is required.** `scripts/demo_mvp.py` needed no changes and its
transcript is unaffected (its `DemoSender.send_image_file` never raises, so the new
`_send_capture_reply` failure branch is never exercised by the demo -- only by the new unit
tests). The chain `docs/agents/mvp-integration-handoff.md` already audited and wired through
`WeChatImageReplyWorkflow.handle()` is unchanged in shape; the three fixes here only make
previously-mishandled failure cases (duplicate filenames, a malformed upload response, a WeChat
send failure) report themselves truthfully instead of either silently corrupting state, crashing
opaquely, or losing stage context to an outer generic exception handler.

Worth a note if `docs/MVP_DEMO.md` or `docs/agents/browser-mvp-handoff.md` are revised later:
`browser-mvp-handoff.md`'s "Known Limitations" #4 ("the newly-fixed `send_image_file` call in
`_run_capture`'s exception branch is itself unguarded... if the WeChat API is *also* down when a
capture fails, that raises out of `_run_capture`/`.handle()`") is **resolved by this session** --
both `send_image_file` call sites in `_run_capture` are now guarded via `_send_capture_reply`.

## Next Step

1. Get the project owner's decision on whether a transient WeChat send failure should ever be
   retried beyond the existing single `AccessTokenInvalidError`-triggered retry (see "Known
   Limitations" #3) -- left as-is here since it's new reliability scope, not a documented
   requirement.
2. This mirrors every prior handoff's standing note: **do not commit** any of this without the
   user explicitly asking (per the project's working agreement referenced in
   `docs/PROJECT_SNAPSHOT.md`).
3. Live WeChat API verification remains open (`docs/TASK_STATUS.md` Task 9) -- unchanged by this
   session, needs real credentials + explicit authorization to contact the live API.
4. `docs/agents/browser-mvp-handoff.md`'s "Known Limitations" #4 can be marked resolved by
   whoever next updates that doc or `docs/PROJECT_SNAPSHOT.md` (see "Is Integration Agent Action
   Required?" above) -- not done here since Rule 3 (`docs/PROJECT_RULES.md`) reserves
   `PROJECT_SNAPSHOT.md` updates for code that's actually been reviewed and merged.
