# Project History

This file is append-only. Each release gets one section, added at the bottom. Prior entries are
never rewritten.

---

## v0.1.0 — 2026-07-20

### Summary

First official MVP release. A WeChat official-account bot that receives chat commands, drives a
real browser session against a BMS/WebStation dashboard over Chrome DevTools Protocol, captures
screenshots (including deep equipment-graphic navigation), stores them per-user/per-channel, and
replies to the user in WeChat with the (optionally watermarked) image. The full chain — WeChat
webhook → message router → equipment selection → browser capture → screenshot storage → WeChat
reply — was built module-by-module, integrated, independently QA'd, and then validated against
real infrastructure (real WeChat account, real Chrome/CDP, real WebStation dashboard) from the
user's own dev machine.

### Major completed milestones

- **Workflow MVP**: `message_router` state machine (channel join, equipment category → item →
  confirm → capture, cancel, watermark commands, private-channel passcode unlock), equipment
  catalog loading from CSV, per-user/per-team selection tracking.
- **Browser MVP**: `BrowserScreenshotService` capture contract over a shared multi-tab CDP
  service — one Chrome instance, one tab per team, real WebStation login and hash-route
  navigation, documented failure surface (never a swallowed exception).
- **Storage / Reply MVP**: `ScreenshotStore` per-user/per-channel filesystem layout with
  same-millisecond dedupe, `WeChatImageSender` upload/send with explicit `media_id` validation,
  and a failure-reply path that guarantees the user always gets a real message (placeholder image
  on capture failure) instead of silence.
- **Project Integration**: all module boundaries (router → workflow → browser → storage → sender)
  cross-checked field-for-field; no integration defects found.
- **QA Acceptance**: independent line-by-line re-audit of the full chain, re-running every test
  and the demo script from scratch rather than trusting prior handoffs.
- **Release Readiness**: independent audit of repo/doc/test consistency prior to live testing.
- **Live Validation**: full real-environment run — real WeChat account, real Chrome/CDP against
  the real WebStation dashboard (`10.121.0.14`), real per-user storage writes, real WeChat
  media upload/send with confirmed `errcode: 0` delivery, and a real public tunnel carrying
  genuine signed WeChat traffic through the entire pipeline. A real WeChat user confirmed
  receiving images in their client.
- Supporting ops tooling added along the way: `Bot.ps1` CLI, public/permanent tunnel scripts,
  Ansible tunnel task, watermark chat customization, hidden backup/passcode-gated channels,
  per-user storage scoping.

### Test count

112 tests passing (0 failed), plus 7 subtests — up from a 110-test baseline after Live
Validation's first-touch-capture-timeout fix added regression coverage.

### Live validation summary

Every stage of the MVP chain was independently exercised against real infrastructure from the
user's own machine: real login across 5 teams, real plain-channel and equipment-path capture,
real per-user/per-channel `ScreenshotStore` writes, real WeChat `access_token`/upload/send calls,
and a real public tunnel with correct signature verification. A real WeChat user's menu taps and
text messages hit the live webhook and received real, confirmed (`errcode: 0`) image deliveries,
client-side receipt confirmed by the user. One Major defect (first-touch capture timeout on
occluded Chrome tabs) was found, root-caused, minimally fixed, and regression-tested — measurably
improved but not 100% eliminated. One process incident (a diagnostic script colliding with the
live webhook's Chrome tab management) was self-diagnosed and fully recovered with no data loss.
No Critical, MVP-breaking defect was found. Final recommendation from that session: **LIVE MVP
VALIDATED — READY TO COMMIT**.

### Known follow-up items

- First-touch capture timeout on occluded browser tabs not fully eliminated (Major, partially
  fixed).
- Cross-process Chrome/CDP tab-management collision risk remains architecturally open
  (`profile_manager.py`'s lock is process-local only); now has a real, live reproduction case.
- Test-coverage gaps: `watermark_commands.py`, `menu.py`, `watermark_settings.py`,
  `wechat/official_api.py`, `wechat/media_downloader.py`, and the private-channel passcode flow
  (`unlock_private`/`join_private`/`private_photo`) have zero dedicated tests.
- No CI, no lint/format tooling (`ruff` not wired up).
- `device-agent-mvp/`'s exposed OpenRouter API key remains unrotated (unrelated, disconnected
  prototype; human action item).
- No state-expiry for the equipment-selection flow; no dedicated duplicate-confirm UX; no retry
  beyond the existing single access-token-invalid retry for WeChat sends — deliberate, pending
  product decisions.
- Split-brain/non-elevated manual restart fix has a code fix in place but was never retested
  against the original real failure scenario.
- Stray throwaway Cloudflare quick-tunnel process from the Live Validation session needs manual
  cleanup (blocked by the environment's permission classifier).
