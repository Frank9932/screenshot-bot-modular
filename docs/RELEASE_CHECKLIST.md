# Release Checklist — v0.1.0

- Date: 2026-07-20
- Branch: `feature/user-scoped-storage-and-channels`
- Base commit before this release: `cbcc8ce`

## Files Modified (18, tracked)

```
.gitignore
README.md
ansible/README.md
ansible/deploy.yml
config.example.json
docs/DEBUG_HANDOFF.md
scripts/Bot.ps1
scripts/Start-WebhookBackground.ps1
scripts/Stop-WebhookBackground.ps1
src/screenshot_bot/browser/README.md
src/screenshot_bot/browser/cdp_multi_tab_service.py
src/screenshot_bot/browser/profile_manager.py
src/screenshot_bot/browser/screenshot_service.py
src/screenshot_bot/screenshot_store/README.md
src/screenshot_bot/screenshot_store/store.py
src/screenshot_bot/wechat/README.md
src/screenshot_bot/wechat/image_sender.py
src/screenshot_bot/wechat/official_api.py
src/screenshot_bot/wechat/webhook_server.py
src/screenshot_bot/workflow/README.md
src/screenshot_bot/workflow/help_text.py
src/screenshot_bot/workflow/wechat_image_reply.py
```

## Files Added (staged for this release)

Production code, ops tooling, and demo assets (per `docs/WORKTREE_INVENTORY.md` categories A/C):

```
ansible/tasks/tunnel.yml
config.mvp_demo.json
scripts/Watch-WebhookLog.ps1
scripts/crawl_graphics_tree.py
scripts/demo_mvp.py
scripts/run_wechat_menu_sync.py
scripts/screenshot_equipment_list.py
src/screenshot_bot/browser/equipment_navigation.py
src/screenshot_bot/wechat/menu_manager.py
src/screenshot_bot/workflow/equipment_catalog.py
src/screenshot_bot/workflow/equipment_prompts.py
src/screenshot_bot/workflow/equipment_selection_tracker.py
src/screenshot_bot/workflow/menu.py
src/screenshot_bot/workflow/message_router.py
tests/  (20 test files across browser/storage/wechat/workflow)
```

Governance/handoff documentation (category B):

```
docs/KNOWLEDGE_RECONCILIATION.md
docs/LIVE_VALIDATION_REPORT.md
docs/MVP_DEMO.md
docs/MVP_TEST_REPORT.md
docs/PROJECT_RULES.md
docs/PROJECT_SNAPSHOT.md
docs/RELEASE_READINESS_REPORT.md
docs/STABILIZATION_PLAN.md
docs/TASK_STATUS.md
docs/WORKTREE_INVENTORY.md
docs/agents/  (13 handoff files)
```

Release Agent deliverables (this session):

```
PROJECT_HISTORY.md
docs/RELEASE_NOTES_v0.1.0.md
docs/SPRINT2_BACKLOG.md
docs/RELEASE_CHECKLIST.md
```

## Explicitly Excluded from this Release

- **`device-agent-mvp/` (entire directory)** — an unrelated, disconnected prototype
  (`docs/TASK_STATUS.md` Task 12), classified "D" (do not commit) by
  `docs/WORKTREE_INVENTORY.md` Section 6. Its `.env` holds a real, still-unrotated API key.
  Not staged, not committed.
- `device-agent-mvp/.env`, `device-agent-mvp/logs/` — gitignored, contain secrets/local logs.
- `config.json` — gitignored, local machine-specific runtime config.
- `secrets.local.ps1`, `ansible/files/secrets.local.ps1` — gitignored, real credentials.
- `/storage/`, `/runtime/`, `/logs/` — gitignored, runtime-generated data (screenshots, webhook
  state, tunnel logs).
- `__pycache__/`, `*.pyc` — gitignored, build artifacts.

A pattern scan (`sk-`, `AKIA`, `xoxb-`, `ghp_`) across everything being staged found no real
secret matches (only a doc's description of the scan methodology and an intentionally-truncated
placeholder token in `ansible/README.md`'s example commands).

## Test Result

112 passed, 0 failed, 7 subtests passed (per `docs/LIVE_VALIDATION_REPORT.md`, final run after
the first-touch-timeout regression test was added; up from a 110-test baseline).

## Live Validation Result

**LIVE MVP VALIDATED — READY TO COMMIT** (`docs/LIVE_VALIDATION_REPORT.md`'s own final
recommendation). Full real-environment run against real WeChat, real Chrome/CDP, and the real
WebStation dashboard; real per-user storage writes; real WeChat media upload/send with confirmed
`errcode: 0` delivery; a real WeChat user confirmed receiving images client-side. One Major defect
(first-touch capture timeout) found, root-caused, and partially fixed with a regression test. One
process incident, self-diagnosed and fully recovered with no data loss. No Critical defect found.

## Ready for Commit

**Yes.** All four review documents (`TASK_STATUS.md`, `LIVE_VALIDATION_REPORT.md`,
`RELEASE_READINESS_REPORT.md`, `MVP_TEST_REPORT.md`) independently converge on the same
conclusion, no accidental temporary files were found in the working tree, and the file set above
excludes every secret, local-only, or unrelated-prototype path.

## Ready for Tag

**Yes**, contingent on the commit above landing cleanly. Tag: `v0.1.0`, message "First live
validated MVP".
