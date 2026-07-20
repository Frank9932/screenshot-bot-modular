# MVP Test Report

- Task: QA Acceptance — independent acceptance review of the complete MVP (see
  `docs/TASK_STATUS.md`)
- Owner: QA Acceptance Agent
- Date: 2026-07-20
- Status at handoff: **review complete, no code changes made**; not committed, not merged, no
  live-environment (real WeChat/Chrome/WebStation) verification

## Environment note

Work was performed directly in the main checkout (`C:\Users\frank\screenshot-bot-modular`,
branch `feature/user-scoped-storage-and-channels`, tip commit `cbcc8ce`, plus the accumulated
uncommitted working-tree changes from four prior MVP sessions). No worktree was created, no
branch was switched, nothing was committed or merged, per this task's explicit instructions.

This review does **not** take any prior agent's conclusions on trust. Every claim in
`docs/agents/workflow-mvp-handoff.md`, `docs/agents/browser-mvp-handoff.md`,
`docs/agents/storage-reply-mvp-handoff.md`, and `docs/agents/project-mvp-integration-handoff.md`
was re-derived independently — by reading the actual source files line by line (not just the
handoffs' summaries of them) and by re-running every command from scratch.

## Executive Summary

The full MVP chain — incoming WeChat message → router → equipment selection → browser capture
→ `ScreenshotStore` → WeChat reply — is **internally consistent, correctly wired, and covered by
a passing automated test suite and a working local demo**, at the "Level C" (local, mocked
Chrome/CDP + mocked WeChat HTTP boundary) scope every project doc already declares. Independent
line-by-line reading of every file in the chain (`message_router.py`,
`equipment_selection_tracker.py`, `equipment_prompts.py`, `user_team_tracker.py`, `help_text.py`,
`wechat_image_reply.py`, `screenshot_service.py`, `equipment_catalog.py`, `store.py`,
`image_sender.py`, `official_api.py`, `media_downloader.py`, `webhook_server.py`,
`xml_message.py`, `signature.py`, `watermark_commands.py`, `watermark_settings.py`, `menu.py`,
`target_config.py`) **confirms every bug-fix claim made by the four prior MVP sessions is
accurate** — the code on disk matches what each handoff says it did. No new code defect that
breaks documented MVP behavior was found.

What this review adds beyond the prior sessions' own (already thorough) self-audits:

1. **A real, previously unflagged test-coverage gap**: `watermark_commands.py`, `menu.py`,
   `watermark_settings.py`, `wechat/official_api.py`, and `wechat/media_downloader.py` have
   **zero dedicated automated tests**, despite watermark customization and the tap-menu being
   named, headline MVP features (see "Known Limitations" below). The private-channel
   passcode/unlock flow (`unlock_private`/`join_private`/`private_photo` in `message_router.py`)
   is also untested except incidentally.
2. **A confirmed documentation inconsistency**: `docs/PROJECT_SNAPSHOT.md`'s Known Issue #2 and
   `docs/agents/storage-reply-mvp-handoff.md`'s "Known Limitations #7" both claim
   `src/screenshot_bot/screenshot_store/README.md` still documents a stale key convention. It
   does not — `git diff` shows the working tree already carries the corrected README (matching
   current code), with no handoff crediting the fix. The docs are stale about their own doc no
   longer being stale.
3. Two minor observations (XML parsing has no size/depth guard; incoming photos from
   channel-less senders are silently archived under a `channel_unassigned` folder) — neither
   breaks documented MVP behavior, so neither was changed, per this task's "only fix if it
   causes incorrect MVP behaviour" instruction.

**No blocking defects were found in the Level C scope.** The primary remaining gap before this
MVP can be called fully done is the same one every prior session already flagged: no live
WeChat/Chrome/WebStation verification has been performed by anyone, ever, in this project.

## Environment

| Item | Value |
|---|---|
| Repo | `C:\Users\frank\screenshot-bot-modular` |
| Branch | `feature/user-scoped-storage-and-channels` |
| Commit (tip, plus uncommitted working-tree changes on top) | `cbcc8ce` |
| OS | Windows 11 Pro |
| Python | 3.12.10 |
| pytest | 9.1.1 |
| Shell | Git Bash (POSIX) |

## Commands Executed

| # | Command | Result |
|---|---|---|
| 1 | `pytest tests -v` | **110 passed, 7 subtests passed, 0 failed, 0 skipped** — 2.16s |
| 2 | `python scripts/demo_mvp.py` | **Exit code 0**, no traceback; full transcript reviewed line by line |
| 3 | `git diff src/screenshot_bot/screenshot_store/README.md` | Confirmed the README fix is real and already present (see Documentation Consistency) |
| 4 | `git status --short` / `cat .gitignore` | Confirmed current ignore rules for `device-agent-mvp/.env`, `config.json` |

## Test Results

```
110 passed, 7 subtests passed in 2.16s
```

- **Passed**: 110
- **Failed**: 0
- **Skipped**: 0
- **Duration**: 2.16s

Breakdown by directory (all passing):

| Directory | Tests | Covers |
|---|---|---|
| `tests/workflow/` | 72 (+4 subtests) | `message_router` state machine, `equipment_catalog` CSV loading, `equipment_selection_tracker`/`user_team_tracker` persistence, capture-reply failure boundary |
| `tests/browser/` | 18 (+3 subtests) | `BrowserScreenshotService.capture()` success/failure paths, `equipment_navigation`, capture-exception containment |
| `tests/storage/` | 9 | `ScreenshotStore` save/dedupe/isolation/failure behavior |
| `tests/wechat/` | 8 | `WeChatImageSender` upload/send success/failure, media_id validation, retry-on-invalid-token |
| `tests/workflow/test_reply_failure_boundary.py` | 3 (subset of the 72 above) | Sender-failure and storage-failure containment through `.handle()` |

This exactly matches the count claimed in `docs/agents/project-mvp-integration-handoff.md` — no
discrepancy found.

## Demo Verification

`python scripts/demo_mvp.py`, exit code 0. Verified against console output line by line:

| Scenario | Verified |
|---|---|
| Normal capture (plain channel) | Yes — Step 1 (`'1'`) and Edge 5a (`'2'`) both produce `ok=True`, `trigger_kind=browser_target`, a real file under `runtime/mvp-demo/screenshots/` |
| Equipment selection (category → item → confirm → capture) | Yes — Steps 2–6: 7-category list from the real 676-row CSV, 52-item category-3 list, confirm prompt, confirmed text, final equipment capture with a distinct `equipment_path`-suffixed filename |
| Out-of-range digit re-prompt | Yes — Edge 1b (`'99'`) returns the same category list with a "无效" prefix, state unchanged |
| Capture requested before confirm | Yes — Edge 2 returns "尚未确认设备..." (`equipment_capture_not_ready`), no capture attempted |
| Malformed input — bare digit with no channel/flow context | Yes — Edge 3 falls to ordinary channel guidance text, not misread as an equipment index |
| Equipment CSV missing → empty-catalog fallback | Yes — Edge 4 returns the empty-catalog text, no crash |
| Browser/CDP failure → placeholder image actually sent | Yes — Edge 5b: `trigger_kind=capture_error`, a real placeholder PNG generated **and** a `[WeChat -> demo-user-006] <image> ...` line printed, confirming the Browser MVP session's fix (`_send_capture_reply` being called on the error path) is live in the code, not just claimed |
| Workflow completion (full round trip, real router/tracker/storage, mocked Chrome+WeChat) | Yes — every step above ran through the real `WeChatImageReplyWorkflow.handle()`, no separate test harness |

Storage-failure and sender-failure scenarios are **not** exercised by the demo script itself
(`DemoBrowser`/`DemoSender` never fail in the scripted run) — this matches what every prior
handoff already stated. Those two scenarios were verified instead via the automated test suite
(see "Acceptance Checklist" below), which is the correct place to exercise them.

## Acceptance Checklist

Per the brief's minimum scenario list — method column states whether verification was via
reading the source directly, an automated test, the demo, or a combination:

| Scenario | Verified | Method |
|---|---|---|
| Help | Yes | Code read (`build_general_help_text`, `GENERAL_HELP_WORDS`) + `PrecedenceTests::test_general_help_wins_over_equipment_stage`. **No dedicated "plain help routing" test exists** — only a precedence test exercises this kind (see "Known Limitations"). |
| Watermark (status/reset/opacity/set_field commands) | Partial | Code read only (`watermark_commands.py`, `watermark_settings.py`, `_handle_watermark_command`) — traced every branch (help/status/reset/opacity/set_field, including the "clear field" and out-of-range-opacity and bad-index cases) and found the logic correct. **Zero automated tests exist for this module** — a real coverage gap, see "Known Limitations". |
| Screenshot request (plain channel) | Yes | Demo Step 1/Edge 5a + code read of `_capture_and_reply`/`_run_capture` |
| Equipment selection (category → item → confirm) | Yes | Demo Steps 2–5 + 40 dedicated `test_message_router.py` cases covering every stage/edge case |
| Cancel | Yes | `test_cancel_from_awaiting_category`, `test_cancel_from_awaiting_equipment`, `PendingConfirmTests::test_cancel`, `test_cancel_from_confirmed` — all four active stages confirmed to accept cancel and converge to the same Idle (`{}`) representation |
| Confirm | Yes | Demo Step 5 + `PendingConfirmTests::test_confirm`/`test_confirm_english_word` |
| Browser failure | Yes | Demo Edge 5b + `test_capture_failure_containment.py` (3 exception types) — placeholder image confirmed actually sent, not just generated |
| Storage failure | Yes | `tests/storage/test_store.py::test_write_permission_failure_propagates_and_leaves_no_partial_record` + `test_reply_failure_boundary.py::test_storage_layer_failure_surfacing_through_capture_is_still_contained` — a `PermissionError` surfacing through `capture()` is still folded into a clean `capture_error` result |
| Sender failure | Yes | `tests/wechat/test_image_sender.py` (upload/send failure, invalid `media_id`, missing `touser`/file) + `test_reply_failure_boundary.py`'s two sender-failure cases (including the double-failure case: capture *and* placeholder-send both fail) |
| Malformed input | Yes | Code read: `xml_message.parse_xml_message` raising on bad XML is caught by `do_POST`'s own try/except (`webhook_server.py:92-114`), never crashes the process; `message_router`'s non-numeric-mid-flow handling (`ChooseCategoryTests`/`ChooseEquipmentTests`'s non-numeric-text tests); watermark command malformed-token fallback to help text (code read, no dedicated test) |
| Repeated requests | Yes | `MessageDedupe` (msgid-keyed, 600s TTL, code read) dedupes identical WeChat retries; `ConfirmedStateTests::test_duplicate_confirm_does_not_crash_falls_to_guidance` covers a duplicate "确认"; `ScreenshotStore`'s `_dedupe_path` (`test_duplicate_filename_does_not_overwrite_prior_save`) covers a same-millisecond repeated save |

## Independent Code Audit Findings

Ranked most-severe first. None of these are blocking for Level C acceptance; all are
opportunities to close before calling this MVP fully done.

### Major

1. **No automated test coverage for the watermark-customization chat commands, the tap-menu
   translation, or the WeChat HTTP client's own mechanics.**
   - Files with zero dedicated tests: `src/screenshot_bot/workflow/watermark_commands.py`,
     `src/screenshot_bot/browser/watermark_settings.py`, `src/screenshot_bot/workflow/menu.py`,
     `src/screenshot_bot/wechat/official_api.py`, `src/screenshot_bot/wechat/media_downloader.py`.
   - Why it matters: `PROJECT_SNAPSHOT.md`'s own one-line project description names "optional
     per-channel watermark customization via chat commands" as a headline MVP feature alongside
     the equipment flow — the equipment flow got 40+ dedicated tests; watermark customization got
     zero. Manual tracing of every branch in `watermark_commands.parse_watermark_command` and
     `WeChatImageReplyWorkflow._handle_watermark_command` (help/status/reset/opacity/set_field,
     the "omit value to clear a field" case, the 0–255 opacity bound, the out-of-range field-index
     `IndexError`) found the logic correct — but "found correct by one reader's manual trace"
     is exactly the state every other module was in before this MVP's test-writing sessions
     started, and is weaker protection against a future regression than a test file.
   - `official_api.py`'s token-cache expiry math (`TOKEN_REFRESH_MARGIN_SECONDS`,
     `INVALID_TOKEN_ERRCODES`), and `encode_multipart`'s boundary construction, are exercised
     only indirectly (via `client=` fakes swapped in at `WeChatImageSender`'s tests) — the real
     `WeChatOfficialClient` class itself is never instantiated in any test.
   - Not fixed here — per this task's brief ("only fix an issue if it causes incorrect MVP
     behaviour"; adding a new test suite is scope creep for an acceptance review, not a bug fix).
     Flagged for `docs/TASK_STATUS.md` Task 5 (Minimal Test Baseline), which is the task this
     naturally belongs to.

2. **The private-channel passcode/unlock flow is untested.** `message_router.py`'s
   `unlock_private`, `join_private`, and `private_photo` kinds — the mechanism behind the
   "passcode-gated private channel" PROJECT_SNAPSHOT names as a headline feature — have no
   dedicated test anywhere in `tests/workflow/test_message_router.py`. Manual trace (see
   "message_router.py" reading above) found the logic correct: `PRIVATE_CHANNEL_WORDS` is inert
   until `private_unlocked` is true, the passcode itself (`PRIVATE_CHANNEL_PASSCODE`) is checked
   independently of any other state, and it's never surfaced in help/guidance text. Given this
   is the one hidden/security-adjacent feature in the MVP, its complete absence from the test
   suite is worth closing before relying on it further.

### Minor

3. **`screenshot_store/README.md`'s "stale key convention" is documented as still-open in two
   places, but is already fixed.** `docs/PROJECT_SNAPSHOT.md` Known Issue #2 and
   `docs/agents/storage-reply-mvp-handoff.md`'s "Known Limitations #7"/"Next Step #4" both state
   this README still documents `{user_id}/tab_{tab}`. Reading the file directly shows it already
   documents the correct current convention
   (`{user_id}/channel_{team_id}/{original,watermarked}`), and `git diff` against the last commit
   confirms this fix is real and already present in the working tree — it just isn't credited to
   any session's handoff. Low impact (a doc that's actually correct, just mislabeled as
   incorrect by other docs), but worth a one-line correction in `PROJECT_SNAPSHOT.md`'s Known
   Issues next time that file is regenerated, so a future session doesn't waste time "fixing"
   something already fixed.

### Observations (not defects, no action needed for MVP acceptance)

4. `wechat/xml_message.py`'s `parse_xml_message` calls `ET.fromstring(body)` directly on the raw
   POST body with no size/depth limit. `do_POST`'s surrounding try/except means a malformed or
   oversized body still can't crash the process or corrupt state — confirmed by reading — so this
   doesn't cause incorrect MVP behavior. Purely a defense-in-depth/resource-exhaustion hardening
   item for a future security pass, not something this review changed.
5. `WeChatImageReplyWorkflow._store_incoming_image` archives an incoming photo under
   `{user}/channel_unassigned` even for a sender who has never joined a channel (the reply they
   receive says "you haven't picked a channel yet," but the photo is still saved). This is
   consistent with the module's own "best-effort archive" design intent (confirmed by reading)
   and isn't a bug — just worth knowing if anyone is later surprised to find `channel_unassigned`
   folders in storage.
6. `device-agent-mvp/.env`'s exposed API key is still present, still un-rotated — re-confirmed
   present this session (not re-read/printed, per this review's own handling of secrets).
   Unchanged from every prior session's flag; already tracked as `docs/TASK_STATUS.md` Task 13,
   blocked on a human action this review cannot take.

## Documentation Consistency

Checked `docs/TASK_STATUS.md`, the four `docs/agents/*-handoff.md` files, and `docs/MVP_DEMO.md`
against the actual code and test results:

| Doc claim | Checked against | Result |
|---|---|---|
| `docs/TASK_STATUS.md` rows 14–17: test counts (72/18/20/110), "no new integration defects" | Re-ran every command | **Accurate** — exact match |
| `docs/agents/workflow-mvp-handoff.md`: 4 specific bug fixes in `message_router.py`/`equipment_selection_tracker.py` | Read the actual source | **Accurate** — every fix described is present in the code exactly as described |
| `docs/agents/browser-mvp-handoff.md`: capture-error placeholder image now actually sent | Read `wechat_image_reply.py`'s `_run_capture`/`_send_capture_reply`; re-ran the demo | **Accurate** — confirmed live in both code and demo output |
| `docs/agents/storage-reply-mvp-handoff.md`: 3 bug fixes (dedupe path, media_id guard, unguarded send) | Read `store.py`, `image_sender.py`, `wechat_image_reply.py` | **Accurate** — all three present exactly as described |
| `docs/agents/storage-reply-mvp-handoff.md` "Known Limitations #7": `screenshot_store/README.md` still stale | `git diff` on that file | **Inaccurate** — already fixed, see Minor Finding #3 above |
| `docs/PROJECT_SNAPSHOT.md` Known Issue #2: same README staleness claim | Same | **Inaccurate**, same root cause |
| `docs/PROJECT_SNAPSHOT.md` Known Issue #4 / Task 13: `device-agent-mvp/.env` not gitignored | `cat .gitignore` | **Partially stale**: `.gitignore` already has `device-agent-mvp/.env` and `device-agent-mvp/logs/` entries (working-tree change, uncommitted) — the ignore-rule gap is closed; the key itself is still unrotated, which is the part that's still accurate |
| `docs/MVP_DEMO.md`: six documented demo scenarios | Re-ran `scripts/demo_mvp.py` | **Accurate** — transcript matches the doc's description scenario-for-scenario |

## Real vs. Mock Boundary (re-confirmed)

Consistent with every prior handoff and `docs/MVP_DEMO.md`'s "Level C" declaration:
- **Real**: `message_router.route_message`, `EquipmentSelectionTracker`/`UserTeamTracker`
  persistence, `equipment_catalog` CSV reads (real 676-row file), `ScreenshotStore` filesystem
  writes, `WatermarkRenderer` (real Pillow rendering), `WeChatImageReplyWorkflow.handle()` itself
  (the exact function the live webhook calls, never mocked), `WeChatWebhookServer`'s outer
  exception containment.
- **Mock/fake**: the Chrome/CDP layer (`CdpMultiTabService`/`BrowserProfileManager`) and the
  WeChat HTTP layer (`WeChatOfficialClient`) — no live credentials or network access were used
  or available this session.

## Known Limitations

1. No live WeChat, Chrome, or BMS (`10.121.0.14`) verification has been performed by any session
   in this project's history — `docs/TASK_STATUS.md` Tasks 8/9/10 remain `Blocked` on real
   credentials, network reachability, and explicit authorization, none of which this review had
   or should assume.
2. Test-coverage gaps in watermark commands, tap-menu translation, the WeChat HTTP client, and
   the private-channel flow (Major findings #1–2 above).
3. No state-expiry mechanism for the equipment-selection flow, no dedicated duplicate-confirm
   UX, no retry beyond the existing single access-token-invalid retry for a transient WeChat send
   failure — all previously flagged by prior sessions as deliberate, pending product decisions;
   unchanged by this review.
4. `device-agent-mvp/`'s exposed API key remains unrotated (`docs/TASK_STATUS.md` Task 13,
   blocked on a human action).
5. No Ruff/lint or CI wiring exists yet (`docs/TASK_STATUS.md` Tasks 6/7, `Not Started` —
   explicitly out of scope for this review).

## Blocked Items

- **Live WeChat round trip** (real `api.weixin.qq.com` upload/send) — needs real
  `WECHAT_APPID`/`WECHAT_APPSECRET`/`WECHAT_OFFICIAL_WEBHOOK_TOKEN` and explicit authorization.
- **Live Chrome/CDP/WebStation capture** — needs network reachability to `10.121.0.14`, real
  `WEBSTATION_USERNAME`/`WEBSTATION_PASSWORD`, and explicit authorization.
- **Real production storage-directory failure** (actual disk-full/ACL-denied on a deployed host)
  — only simulated via `unittest.mock.patch` in tests; not reproduced on any real host.
- **API key rotation** for `device-agent-mvp/.env` — requires a human operator
  (`docs/TASK_STATUS.md` Task 13).

## Go / No-Go Recommendation

**Go, for Level C (local, mocked-Chrome/mocked-WeChat) scope.** The complete execution chain —
router, equipment selection, browser-capture contract, storage, and WeChat reply, including every
documented failure mode — is verified consistent end-to-end by both an independent code audit and
a full passing test suite (110/110) and demo (exit 0), with no previously-unknown defect found
that breaks documented behavior. The four prior MVP sessions' bug-fix claims all check out against
the actual code.

**No-Go for anything beyond Level C** (production deployment, or any claim of full end-to-end
correctness against the real WeChat API / real Chrome / real WebStation dashboard) — this remains
completely unverified, as it has been since the project's first MVP session, and requires real
credentials, network reachability, and explicit authorization this review does not have.

**Recommended before the next QA pass**: close the two Major test-coverage gaps (watermark
commands + tap menu, and the private-channel flow) — both are headline MVP features currently
protected only by one reader's manual trace rather than a regression test.

## Next Step

1. **User decision on committing**: per the project's standing working agreement (referenced in
   `docs/PROJECT_SNAPSHOT.md` and every prior MVP handoff), none of the accumulated uncommitted
   work (module fixes, tests, docs, this report) should be committed without the user explicitly
   asking. This session made no commits.
2. Consider assigning the two Major test-coverage gaps (watermark commands/menu/HTTP client,
   private-channel flow) to `docs/TASK_STATUS.md` Task 5 (Minimal Test Baseline), which already
   exists and is `Not Started`.
3. Correct `docs/PROJECT_SNAPSHOT.md` Known Issue #2 (screenshot_store/README.md staleness) next
   time that snapshot is regenerated — it's describing an already-fixed problem.
4. Live-environment verification (`docs/TASK_STATUS.md` Task 8/9/10) remains the single biggest
   gap before this MVP can be called fully done — unchanged by this review.
5. `device-agent-mvp/`'s exposed API key (`docs/TASK_STATUS.md` Task 13) still needs the user's
   direct attention.
