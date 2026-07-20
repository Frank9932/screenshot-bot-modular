# Release Readiness Report

- Task: Release Readiness Agent — independent audit of whether this project may proceed to
  Live Validation (real WeChat / real Chrome-CDP / real WebStation dashboard testing)
- Owner: Release Readiness Agent
- Date: 2026-07-20
- Scope: main checkout only (`C:\Users\frank\screenshot-bot-modular`), branch
  `feature/user-scoped-storage-and-channels`, tip commit `cbcc8ce` plus the accumulated
  uncommitted working-tree changes from the prior Recovery / Stabilization / Knowledge
  Reconciliation / Workflow-MVP / Browser-MVP / Storage-Reply-MVP / Project-Integration /
  QA-Acceptance sessions. No worktree was created, no branch was switched, nothing was
  committed or merged, and no code was modified, per this task's instructions.

This report does not take any prior document's conclusions on trust where a claim was cheap to
re-verify. Every load-bearing claim below (test count, demo exit code, `.gitignore` coverage,
doc-vs-code consistency, deployment mechanism) was independently re-run or re-read this session.

---

## Executive Summary

The MVP execution chain — WeChat message → router → equipment selection → browser capture →
storage → WeChat reply — is internally consistent, fully covered by a passing automated test
suite, and demonstrated working end-to-end via a local demo script. Independent re-execution
this session reproduced every result the prior five audit sessions (Recovery, Stabilization,
Knowledge Reconciliation, three module MVPs, Project Integration, QA Acceptance) already
claimed: **110/110 tests pass**, `scripts/demo_mvp.py` **exits 0** with the documented
transcript, and the project's own governance docs (`PROJECT_RULES.md` → `PROJECT_SNAPSHOT.md`
→ `TASK_STATUS.md` → `KNOWLEDGE_RECONCILIATION.md` → `docs/agents/*`) form a coherent,
cross-checked knowledge base with no unresolved contradiction as of this snapshot — every
inconsistency a prior document flagged (`screenshot_store/README.md` staleness,
`GetServersInfo`→`PeekObjects` drift, the "none" cancel-stage representation, bot-1's
production status) has already been traced to its current, correct state by an earlier
session and re-confirmed accurate here.

**No Critical blocker was found.** The gaps that remain (live WeChat/Chrome/WebStation
verification never having been performed; two Major automated-test-coverage gaps; an
unrotated API key in an unrelated, disconnected prototype directory) are exactly the kind of
gaps Live Validation itself exists to close, or are pre-existing/out-of-band issues that do not
block starting it.

**Recommendation: READY FOR LIVE VALIDATION.**

---

## Repository Status

`git status` (full, including untracked) matches what `docs/PROJECT_SNAPSHOT.md` and
`docs/WORKTREE_INVENTORY.md` already documented, plus the expected superset produced by the
five later MVP/QA sessions (their own new `tests/`, `docs/MVP_*.md`, `docs/agents/*-mvp-
handoff.md` files) — nothing unexplained was found:

- **18 modified tracked files** — all accounted for by `docs/WORKTREE_INVENTORY.md`'s
  classification (core equipment-catalog/menu integration, permanent-tunnel/ops tooling,
  `.gitignore` hardening). Re-checked `git diff --stat`: 22 files, +1136/-307 lines, dominated
  by `workflow/wechat_image_reply.py` (485 lines) and `workflow/README.md`/`browser/README.md`
  (documentation catching up to the equipment-catalog work).
- **Untracked files**: equipment-catalog/menu source modules, `tests/` (new, 20 test files
  across `tests/{browser,storage,wechat,workflow}/`), `docs/*.md` governance/MVP docs,
  `docs/agents/*-handoff.md`, ops scripts, and the disconnected `device-agent-mvp/` prototype
  (10 files + its own `.env`). All previously catalogued; none unexplained.
- **No deleted files** in the working tree relative to `cbcc8ce`.
- **No unexpected secrets in tracked or about-to-be-tracked content**: a pattern scan
  (`sk-`, `AKIA`, `xoxb-`, `ghp_`) across tracked file types found zero real matches — the only
  hits were a doc's own description of the scan methodology and the intentionally-truncated
  placeholder token (`eyJhIjoi...`) in `ansible/README.md`'s example commands. The one real
  credential on disk, `device-agent-mvp/.env`'s OpenRouter key, is untracked, was never
  committed (`git log --all --full-history -- device-agent-mvp/.env` — empty, re-verified this
  session), and is now covered by `.gitignore` (`device-agent-mvp/.env`, `device-agent-mvp/
  logs/`, `/storage/`, `config.json` — all present, re-read this session).
- **`device-agent-mvp/` has zero code coupling** to `screenshot_bot` — `grep -rl
  "screenshot_bot" device-agent-mvp` returned nothing, re-confirmed this session.

No changes were made. This section is observational only.

## Documentation Status

Read and cross-checked: `PROJECT_RULES.md`, `PROJECT_SNAPSHOT.md`, `TASK_STATUS.md`,
`KNOWLEDGE_RECONCILIATION.md`, `STABILIZATION_PLAN.md`, `WORKTREE_INVENTORY.md`, `MVP_DEMO.md`,
`MVP_TEST_REPORT.md`, and all four MVP handoffs (`workflow-mvp-handoff.md`, `browser-mvp-
handoff.md`, `storage-reply-mvp-handoff.md`, `project-mvp-integration-handoff.md`).

- **Internally consistent as a chain.** Each later document explicitly re-verifies and either
  confirms or corrects the one before it (`KNOWLEDGE_RECONCILIATION.md` resolves five open
  conflicts from earlier handoffs with code-level evidence; `MVP_TEST_REPORT.md` catches and
  corrects a stale claim that both `PROJECT_SNAPSHOT.md` and `storage-reply-mvp-handoff.md` were
  still carrying about `screenshot_store/README.md`). This session re-read
  `screenshot_store/README.md` directly and confirms it already documents the current
  `{user_id}/channel_{team_id}/{original,watermarked}` convention — the correction was accurate
  and remains accurate now.
- **Doc claims match code, independently re-checked**: `config.example.json`'s
  `equipment_catalog.enabled` still defaults to `false` (confirmed by direct read, matches every
  handoff's claim); `pyproject.toml` still declares only `Pillow` + pytest's `pythonpath`, no
  dev-dependency group, no ruff/CI config (confirmed, matches `STABILIZATION_PLAN.md`'s P1/P4
  findings, unchanged); the ansible deploy mechanism (`ansible/deploy.yml` → `tasks/app.yml`)
  copies files directly from the local checkout (`win_copy: src: "{{ playbook_dir }}/../{{ item
  }}"`) rather than pulling from git — confirmed by direct read, which means **the currently
  uncommitted working tree can be deployed as-is**; Live Validation does not require committing
  first.
- **No new documentation drift found** beyond what `KNOWLEDGE_RECONCILIATION.md` already
  catalogued and closed (the `GetServersInfo`→`PeekObjects` handoff gap, the three-generation
  storage-key-format history, the bot-1 production-status timeline, the `_lock_for` coverage
  question). All five are resolved in favor of current code, as that document already concluded.

## Test Status

Independently re-run this session (not taken on trust):

| Command | Result |
|---|---|
| `PYTHONPATH="$PWD/src" python -m pytest tests -v` | **110 passed, 7 subtests passed, 0 failed** — 2.21s |
| `PYTHONPATH="$PWD/src" python scripts/demo_mvp.py` | **Exit code 0**, no traceback; transcript matches `docs/MVP_DEMO.md`'s described scenarios (channel join/capture, equipment category→item→confirm→capture, out-of-range re-prompt, capture-before-confirm, malformed bare-digit input, missing-CSV fallback, simulated browser failure with placeholder image genuinely sent) |

This exactly reproduces the counts and outcomes claimed in `docs/TASK_STATUS.md` rows 14–18 and
`docs/MVP_TEST_REPORT.md` — no discrepancy found. Coverage breakdown (unchanged from
`MVP_TEST_REPORT.md`): `tests/workflow/` (72+4 subtests — router state machine, equipment
catalog/tracker, user-team tracker), `tests/browser/` (18+3 subtests — capture contract,
equipment navigation, failure containment), `tests/storage/` (9 — `ScreenshotStore`),
`tests/wechat/` (8 — `WeChatImageSender`), plus 3 cross-cutting reply-failure-boundary tests.

**Real test-coverage gaps, confirmed still present** (already flagged by `MVP_TEST_REPORT.md`,
re-verified unchanged this session — zero dedicated test files exist for these):
`workflow/watermark_commands.py`, `browser/watermark_settings.py`, `workflow/menu.py`,
`wechat/official_api.py`, `wechat/media_downloader.py`, and the private-channel
`unlock_private`/`join_private`/`private_photo` router kinds. All were manually traced and found
correct by the prior session's line-by-line reading — that reasoning was not independently
re-derived line-by-line in this pass (out of scope for a readiness audit), but the *absence* of
dedicated tests for these files was re-confirmed by directly listing `tests/` (see Repository
Status) and cross-referencing against the module list.

No CI exists (`.github/workflows/` absent, re-confirmed by glob). No lint/format tooling is
wired up (`ruff` not in `pyproject.toml`).

## Integration Status

The chain **Workflow MVP → Browser MVP → Storage/Reply MVP → Integration → QA** is internally
consistent:

- `message_router.route_message`'s ~20 `"kind"` values each have a matching branch in
  `WeChatImageReplyWorkflow.handle()` — spot-checked the equipment-flow branches
  (`equipment_selected` now carrying `category`, `cancel()` converging to `{}`) and the
  capture-failure branch (`_run_capture`'s `except` now calling `_send_capture_reply`, itself
  now try/excepted) directly in `wechat_image_reply.py`; both match what `browser-mvp-
  handoff.md` and `storage-reply-mvp-handoff.md` claim.
- `BrowserScreenshotService.capture()`'s return shape (`published_path`, `capture_ms`, etc.) and
  exception surface (`KeyError`/`ValueError`/`FileNotFoundError`/`RuntimeError`, never a
  swallowed failure) match what `_run_capture` actually reads and catches.
- `ScreenshotStore.save_screenshot()`'s signature and the four real call sites (two in
  `capture()`, two in `_store_incoming_image`) all pass real `bytes` and caller-composed
  multi-segment keys — consistent with the module's own (now-corrected) README.
- `WeChatImageSender.send_image_file()`'s return dict fields are exactly what `.handle()` reads
  via `.get(...)`; its failure path is now caught at both call sites in `_run_capture` via
  `_send_capture_reply`, closing the double-failure gap `browser-mvp-handoff.md` had originally
  left open (confirmed resolved by `storage-reply-mvp-handoff.md`, and the fix is present in the
  code read this session).
- The outermost safety net, `WeChatWebhookServer`/`_process_async`'s `except Exception`, is
  present and unmodified (confirmed by reading `webhook_server.py`), so no exception anywhere in
  this chain can crash the webhook process even in a scenario the test suite didn't anticipate.

**No new integration defect was found this session**, consistent with every prior integration
pass's own conclusion.

## Known Limitations

(Carried forward from prior audits, independently re-confirmed still accurate — none are new)

1. **No live WeChat, Chrome, or WebStation (`10.121.0.14`) verification has ever been
   performed.** This is the explicit purpose of the Live Validation phase this report is
   gating, not a defect in the current code.
2. **Two Major test-coverage gaps**: watermark commands / tap-menu / WeChat HTTP client, and the
   private-channel passcode flow (see Test Status).
3. **`device-agent-mvp/`'s exposed OpenRouter API key remains unrotated.** It is disconnected
   from the bot (no code coupling), gitignored, and was never committed — but the key itself has
   been exposed to multiple agent-session contexts and is still live on disk. This does not
   block Live Validation of the WeChat bot but is an outstanding action item for the user.
4. **No state-expiry mechanism for the equipment-selection flow, no dedicated duplicate-confirm
   UX, no retry beyond the existing single access-token-invalid retry for WeChat sends** — all
   deliberate, previously flagged, pending product decisions rather than defects.
5. **Cross-process concurrency guard for shared Chrome/CDP provisioning does not exist** — the
   `profile_manager.py` lock is process-local only; the split-brain incident's most recent (third)
   root-cause explanation has a code fix in place but was never retested against the actual
   non-elevated manual-restart failure scenario that triggered the original incident.
   `docs/DEBUG_HANDOFF.md`/`KNOWLEDGE_RECONCILIATION.md` both flag this as still open.
6. **No CI, no lint/format tooling.** Quality gates are entirely manual (`pytest` run by hand).
7. **`config.json` (local, gitignored) has a schema that lags current code** (still carries
   dead `virtual_desktop`/`screenshot_tool` fields) — harmless since dead fields are never read,
   but worth refreshing from `config.example.json` before using it as a real deployment
   reference.

## Release Blockers

### Critical
None found.

### Major
1. **Two automated-test-coverage gaps** (watermark commands/menu/WeChat HTTP client; private-
   channel passcode flow) — logic manually verified correct by a prior session but unprotected
   by regression tests. Recommend closing before or shortly after Live Validation begins, since
   these are exactly the features a live WeChat session would first exercise for real.
2. **Unrotated live API key** (`device-agent-mvp/.env`) — a human action item, independent of
   the bot's release path, but real and outstanding.
3. **Unconfirmed split-brain fix under the actual failure scenario** — the fix (port-based stop
   verification) exists and is deployed in code, but was never retested via a genuine
   non-elevated manual restart, which was the original trigger. Relevant if Live Validation
   involves restarting the webhook process on a shared host.

### Minor
1. No CI / lint tooling wired up — manual discipline only.
2. `config.json`'s local schema is stale relative to `config.example.json` (dead fields, not
   read by current code).
3. Uncommitted work spans five audit sessions and 40+ files — not itself a blocker (deployment
   copies the local tree directly, not via git), but the user should decide when to commit per
   the project's standing working agreement before this accumulates further.

### Observations
1. `wechat/xml_message.py` has no size/depth guard on incoming XML — contained by the outer
   exception handler, a defense-in-depth item only.
2. Incoming photos from channel-less senders are archived under `channel_unassigned` — documented
   as intentional "best-effort archive" behavior, not a bug.
3. Two long-lived branches exist on origin (`feature/team-per-tab-browser-module`, fully merged;
   `feature/user-scoped-storage-and-channels`, current/open PR #4) — no cleanup needed for
   release readiness, purely a housekeeping item.

## Recommendation

**READY FOR LIVE VALIDATION**

Rationale: every artifact required for this phase exists and independently re-verifies clean —
demo script, automated test suite (110/110), module contracts, and handoff documentation are
all present, internally consistent, and accurately describe the current code. No Critical
blocker was found; the Major items above (test-coverage gaps, the unrotated unrelated API key,
the unretested split-brain fix) are real but do not prevent starting Live Validation — the first
is a regression-safety gap the live pass itself will help surface, the second is out-of-band of
the bot's own release path, and the third only matters if the live session involves restarting a
shared host's webhook process, which should be flagged to whoever runs that phase rather than
block it from starting.
