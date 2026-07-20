# Release Report

- Date: 2026-07-20
- Owner: Release Agent
- Branch: `feature/user-scoped-storage-and-channels`

## Release Summary

The first official MVP release (v0.1.0) of the WeChat screenshot bot was prepared and committed
directly in the main checkout, per this task's instructions (no worktree used). Four independent
review documents (Task Status, Live Validation, Release Readiness, MVP Test Report) were read and
cross-checked; no accidental temporary files were found in the working tree — everything
transient (`runtime/`, `storage/`, `logs/`, `__pycache__/`, `device-agent-mvp/.env`,
`device-agent-mvp/logs/`) was already correctly gitignored, and the one file that looked
demo-adjacent (`config.mvp_demo.json`) was confirmed to be a real, intentional config referenced
by `scripts/demo_mvp.py`, not debug noise.

`PROJECT_HISTORY.md` was created with a v0.1.0 entry (append-only, no prior history existed).
`docs/RELEASE_NOTES_v0.1.0.md` and `docs/SPRINT2_BACKLOG.md` were written. `docs/RELEASE_CHECKLIST.md`
documents the exact file set staged for this release. 75 files (18 modified + 57 added) were
staged and committed in a single release commit; `device-agent-mvp/` (an unrelated, disconnected
prototype explicitly classified "do not commit" by the project's own `docs/WORKTREE_INVENTORY.md`,
and holding a real unrotated API key in its gitignored `.env`) was deliberately excluded. An
annotated tag `v0.1.0` was created on the release commit. Nothing was pushed or merged.

## Commit SHA

```
e7c594269e5e326d2f6a39059a94edc46e7c5653
```

Subject: `feat: release MVP v0.1.0`

## Tag

```
v0.1.0 -> e7c594269e5e326d2f6a39059a94edc46e7c5653
Message: "First live validated MVP"
```

## Files Changed

75 files changed, 8964 insertions(+), 307 deletions(-) — 18 modified (tracked production code,
READMEs, ops scripts), 57 added (equipment-catalog/menu/tunnel production modules, 20 new test
files across `tests/{browser,storage,wechat,workflow}/`, 13 `docs/agents/*-handoff.md` governance
documents, 8 project-level docs, and this session's 4 release deliverables). Full breakdown in
[`docs/RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md). `device-agent-mvp/` (10 files) remains
untracked and excluded, exactly as before this release.

## Test Summary

**112 passed, 0 failed, 7 subtests passed** (per `docs/LIVE_VALIDATION_REPORT.md`'s final run,
up from a 110-test baseline before Live Validation's regression test for the Chrome
first-touch-timeout fix). `scripts/demo_mvp.py` exits 0 with a transcript matching
`docs/MVP_DEMO.md`.

## Live Validation Summary

Full real-environment validation was independently performed and confirmed working: real WeChat
account, real Chrome/CDP against the real WebStation dashboard (`10.121.0.14`), real per-user/
per-channel `ScreenshotStore` writes, real WeChat `access_token`/media-upload/send calls with
confirmed `errcode: 0` delivery, and a real public tunnel carrying genuine signed WeChat traffic
through the full router → capture → storage → send pipeline. A real WeChat user's own menu taps
and text messages hit the live webhook and received confirmed image deliveries, with client-side
receipt confirmed by the user. One Major defect (first-touch capture timeout on occluded Chrome
tabs) was found, root-caused, minimally fixed, and regression-tested — measurably improved but
not 100% eliminated. One process incident (a diagnostic script colliding with the live webhook's
own Chrome tab management) was self-diagnosed and fully recovered with no data loss. **No
Critical, MVP-breaking defect was found.** The session's own final recommendation: **LIVE MVP
VALIDATED — READY TO COMMIT**.

## Remaining Backlog

Full detail in [`docs/SPRINT2_BACKLOG.md`](SPRINT2_BACKLOG.md). Summary:

- **P1**: close the first-touch capture timeout fully; add a cross-process Chrome/CDP concurrency
  guard (real reproduction this cycle, not just theoretical); add automated tests for watermark
  commands/tap-menu/WeChat HTTP client/private-channel passcode flow; rotate the exposed
  `device-agent-mvp` API key (human action).
- **P2**: retest the split-brain/non-elevated-restart fix against its original real failure
  scenario; wire up CI + Ruff/lint tooling; get a human product decision on state-expiry/
  duplicate-confirm/send-retry UX; clean up a stray leftover quick-tunnel process.
- **P3**: refresh `config.json`'s local schema; correct a now-stale doc claim in
  `PROJECT_SNAPSHOT.md`; reconcile `TASK_STATUS.md` rows 8–10 against what Live Validation
  actually already covered; the disconnected `device-agent-mvp` prototype track.

## Recommendation

**READY TO PUSH**
