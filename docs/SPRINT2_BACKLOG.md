# Sprint 2 Backlog

Compiled from unresolved items in `docs/MVP_TEST_REPORT.md` (QA Acceptance),
`docs/RELEASE_READINESS_REPORT.md`, and `docs/LIVE_VALIDATION_REPORT.md`. No Sprint 2 work is
implemented here — this is planning only.

---

## P1

### 1. Close the first-touch browser capture timeout

- **Description**: The first `Page.captureScreenshot` call on any tab that was only logged into
  (never previously screenshotted) can still time out even after Live Validation's mitigating
  Chrome launch flags (`--disable-backgrounding-occluded-windows` etc.) — reproduced 2 more times
  post-fix, both recovering instantly on retry. Root cause is Chrome throttling rendering on
  occluded/background tabs.
- **Origin**: Live Validation Report, Defect #1 (Major, partially fixed).
- **Suggested approach**: Have `warm_up()` perform one throwaway screenshot per tab at startup so
  the "first slow paint" cost is paid before any real user request, rather than continuing to
  raise the capture timeout. This is the deliberate product/architecture decision the Live
  Validation session explicitly deferred.

### 2. Add a real cross-process Chrome/CDP concurrency guard

- **Description**: `profile_manager.py`'s lock is process-local only. Two processes managing the
  same Chrome instance can close each other's tabs — this session reproduced it for real (a
  diagnostic script collided with the live webhook process and closed 4 real tabs), not just
  theoretically as prior docs had flagged.
- **Origin**: Live Validation Report, Incident #3; Release Readiness Report, Known Limitation #5.
- **Suggested approach**: An OS-level named mutex or lock file (not just an in-process lock) so a
  second process attempting to manage the same Chrome debug port fails fast instead of silently
  reconciling and closing tabs it doesn't own.

### 3. Add automated tests for watermark commands, tap-menu, WeChat HTTP client, and the private-channel flow

- **Description**: `watermark_commands.py`, `menu.py`, `watermark_settings.py`,
  `wechat/official_api.py`, `wechat/media_downloader.py`, and the private-channel
  `unlock_private`/`join_private`/`private_photo` router kinds have zero dedicated tests. Logic
  was manually traced and found correct, but headline MVP features (watermark customization,
  passcode-gated private channels) are currently unprotected against regression.
- **Origin**: MVP_TEST_REPORT.md, Major findings #1–2; Release Readiness Report, Major #1.
- **Suggested approach**: This is exactly `docs/TASK_STATUS.md` Task 5 (Minimal Test Baseline).
  Prioritize the private-channel passcode flow first (security-adjacent), then watermark
  commands/menu, then `official_api.py`'s token-cache/multipart-encoding mechanics.

### 4. Rotate the exposed `device-agent-mvp` API key

- **Description**: A real OpenRouter key has been present on disk (`device-agent-mvp/.env`) and
  exposed to multiple agent-session contexts across this project's history. It is gitignored and
  was never committed, but the key itself is still live.
- **Origin**: MVP_TEST_REPORT.md Known Limitation #4; Release Readiness Report Major #2;
  `docs/TASK_STATUS.md` Task 13.
- **Suggested approach**: Human operator rotates the key at the provider and confirms the old one
  is invalidated. No code change needed — this cannot be done by an agent.

---

## P2

### 5. Retest the split-brain / non-elevated manual restart fix against the real failure scenario

- **Description**: A port-based stop-verification fix exists and is deployed in code, but has
  never been retested against the actual non-elevated manual-restart failure that originally
  triggered the split-brain incident.
- **Origin**: Release Readiness Report, Major #3; `docs/TASK_STATUS.md` Task 11.
- **Suggested approach**: Reproduce the original failure scenario on a non-production target host
  (not bot-1) and confirm the fix holds, per Task 11's own "Next Step."

### 6. Wire up CI and lint/format tooling

- **Description**: No `.github/workflows/`, no `ruff` in `pyproject.toml`. All quality gates are
  manual (`pytest` run by hand).
- **Origin**: Release Readiness Report, Minor #1; `docs/TASK_STATUS.md` Tasks 6/7.
- **Suggested approach**: Add `ruff` as a dev dependency and a pre-commit or CI check once Task 5
  (test baseline expansion) stabilizes; then add a minimal CI workflow running `pytest` + `ruff`
  on push.

### 7. Decide pending product UX questions

- **Description**: No state-expiry mechanism for the equipment-selection flow, no dedicated
  duplicate-confirm UX, no retry beyond the existing single access-token-invalid retry for WeChat
  sends. All previously flagged as deliberate but undecided.
- **Origin**: MVP_TEST_REPORT.md Known Limitation #3; Release Readiness Report Known Limitation
  #4; `docs/TASK_STATUS.md` Task 14's "Next Step."
- **Suggested approach**: Needs a human product decision, not an engineering judgment call —
  bring these three questions to the user explicitly rather than guessing a default.

### 8. Clean up the stray quick-tunnel process

- **Description**: A throwaway Cloudflare quick-tunnel process from the Live Validation session
  is still running, redundant now that the user's permanent tunnel is in use. The environment's
  permission classifier blocked every attempt to stop it from within an agent session.
- **Origin**: Live Validation Report, Remaining Blockers #1.
- **Suggested approach**: User stops the process directly, or adjusts the permission
  configuration to allow `Stop-Process`/`Stop-PublicTunnel.ps1` for this class of cleanup.

---

## P3

### 9. Refresh `config.json`'s local schema

- **Description**: The local, gitignored `config.json` still carries dead `virtual_desktop`/
  `screenshot_tool` fields that current code never reads. Harmless but stale.
- **Origin**: Release Readiness Report, Minor #2; Known Limitation #7.
- **Suggested approach**: Regenerate from `config.example.json` next time `config.json` is
  touched for a deployment; not urgent since dead fields are inert.

### 10. Correct `PROJECT_SNAPSHOT.md` Known Issue #2

- **Description**: `PROJECT_SNAPSHOT.md` and an earlier handoff both still describe
  `screenshot_store/README.md` as stale/documenting an old key convention. It was already fixed;
  the doc describing it as broken is itself now the stale artifact.
- **Origin**: MVP_TEST_REPORT.md, Minor finding #3.
- **Suggested approach**: One-line correction next time `PROJECT_SNAPSHOT.md` is regenerated.

### 11. Reconcile `TASK_STATUS.md` rows 8–10 now that real live testing has occurred

- **Description**: Tasks 8 (Equipment Menu Live Verification), 9 (Incoming WeChat Image Storage
  Verification), and 10 (Browser Session Recovery Verification) are still marked `Blocked` in
  `docs/TASK_STATUS.md`, but Live Validation performed real equipment-path capture, real storage
  writes, and exercised real browser failure/recovery paths this session. These rows may now be
  answerable as `Completed` or at least `Review`.
- **Origin**: Cross-reference of `docs/TASK_STATUS.md` rows 8–10 against `docs/LIVE_VALIDATION_REPORT.md`.
- **Suggested approach**: A short doc-only pass to update `TASK_STATUS.md` against what Live
  Validation actually covered, rather than engineering work.

### 12. Device Agent MVP track

- **Description**: `device-agent-mvp/`'s `parse_index_reference` fix exists but is unverified,
  and the whole prototype remains disconnected from the production bot.
- **Origin**: `docs/TASK_STATUS.md` Task 12.
- **Suggested approach**: Low priority — out of scope for the bot's own release path; revisit only
  if `device-agent-mvp` is ever promoted beyond prototype status.
