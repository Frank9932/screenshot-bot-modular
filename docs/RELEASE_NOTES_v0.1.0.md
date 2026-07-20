# Release Notes — v0.1.0

- Date: 2026-07-20
- Status: First official MVP release, live-validated, ready to commit.

## New Features

- **WeChat chat-driven screenshot capture.** A WeChat official-account user can join a channel,
  request a screenshot of the plain dashboard, or drill into a specific equipment graphic
  (category → item → confirm → capture) and receive the resulting image back in chat.
- **Equipment catalog navigation.** A CSV-backed equipment catalog (676 real rows) drives a
  category → item selection flow, with out-of-range/cancel/duplicate-confirm handling.
- **Per-user, per-channel screenshot storage.** Every capture is written under
  `{user_id}/channel_{id}/{original,watermarked}`, isolated per user and per channel, with
  same-millisecond dedupe so rapid repeated captures never silently overwrite each other.
- **Watermark customization via chat commands.** Users can view status, reset, and adjust
  watermark opacity/fields per channel.
- **Hidden backup and passcode-gated private channels.** A private-channel flow
  (`unlock_private`/`join_private`/`private_photo`) gates access behind a passcode, independent
  of normal channel state.
- **Public and permanent tunnel support.** New Ansible tunnel task and PowerShell tooling
  (`Start-PublicTunnel.ps1`, permanent Cloudflare tunnel wiring) to expose the local webhook to
  real WeChat traffic.
- **`Bot.ps1` operator CLI** for browser warmup, webhook lifecycle, and tunnel management.

## Architecture

- WeChat webhook (`wechat/webhook_server.py`) → signature verification → `message_router` state
  machine → `WeChatImageReplyWorkflow` → `BrowserScreenshotService` (shared multi-tab CDP
  service) → `ScreenshotStore` → `WeChatImageSender`.
- One Chrome instance is shared across all configured teams, one tab per team, via
  `CdpMultiTabService` — replacing an earlier one-Chrome-per-target model.
- The outermost `except Exception` in the webhook process guarantees no failure anywhere in the
  chain can crash the server; every failure degrades to a clean, logged result and a real reply
  to the user (never silence, never a false success).

## Browser Improvements

- Shared multi-tab CDP service replaces the previous one-Chrome-per-target model, reducing
  resource usage and login overhead across teams.
- Equipment-graphic navigation via the WebStation SPA's hash routing, verified against a real
  676-row equipment catalog.
- Chrome launch flags (`--disable-backgrounding-occluded-windows`,
  `--disable-renderer-backgrounding`, `--disable-background-timer-throttling`) added to reduce
  first-touch capture timeouts on background/occluded tabs (Major defect found and partially
  fixed during Live Validation — see Known Issues).
- Documented capture contract: inputs/outputs, timeout behavior, and every failure mode
  (`KeyError`/`ValueError`/`FileNotFoundError`/`RuntimeError`), none of which are swallowed.

## Workflow Improvements

- Fixed: cancel now only takes effect while `awaiting_confirm`; non-numeric input during
  selection is no longer misread as guidance text; `cancel()` converges to a single Idle
  representation instead of an extra "none" state.
- Unified `equipment_selected` return fields across the router.
- Capture-failure replies now always reach the user: the previous silent-failure path (an
  exception during capture producing `ok=True` with no actual message sent) is closed —
  `_send_capture_reply` guarantees a real placeholder image is sent on any capture error.

## Storage Improvements

- Same-millisecond duplicate saves no longer silently overwrite each other (`_dedupe_path` counter
  suffix).
- `WeChatImageSender` validates `media_id` presence explicitly and raises a clear `RuntimeError`
  instead of a bare `KeyError` on a malformed upload response.
- Both `send_image_file` call sites in the capture-reply path are now guarded, so a send failure
  can no longer escape `.handle()` and lose the already-captured screenshot/storage state.

## Testing

- 112 tests passing, 0 failed, plus 7 subtests (up from a 110-test baseline; +2 from Live
  Validation's regression test for the Chrome launch-flag fix).
- Coverage: `tests/workflow/` (72+4 subtests — router state machine, equipment catalog/tracker),
  `tests/browser/` (18+3 subtests — capture contract, equipment navigation, failure containment,
  Chrome launch flags), `tests/storage/` (9 — `ScreenshotStore`), `tests/wechat/` (8 —
  `WeChatImageSender`), plus 3 cross-cutting reply-failure-boundary tests.
- `scripts/demo_mvp.py` exercises the full chain end-to-end with a real router/tracker/storage
  and a mocked Chrome/WeChat boundary (Level C), exit code 0.
- Known gaps: `watermark_commands.py`, `menu.py`, `watermark_settings.py`,
  `wechat/official_api.py`, `wechat/media_downloader.py`, and the private-channel passcode flow
  have zero dedicated tests (manually traced and found correct, but unprotected by regression
  tests).

## Live Validation

Full real-environment validation was performed from the user's own dev machine against real
infrastructure: real WeChat account, real Chrome/CDP against the real WebStation dashboard
(`10.121.0.14`), real per-user/per-channel storage writes, real WeChat `access_token`/media-upload
/send calls with confirmed `errcode: 0` delivery, and a real public tunnel carrying genuine signed
WeChat traffic through the full pipeline. A real WeChat user's own menu taps and text messages hit
the live webhook and received confirmed image deliveries, with client-side receipt confirmed by
the user. See [`docs/LIVE_VALIDATION_REPORT.md`](LIVE_VALIDATION_REPORT.md) for full detail.

## Known Issues

- **Major (partially fixed)**: first-touch screenshot capture on a browser tab that was only
  logged into (never previously screenshotted) can still occasionally time out due to Chrome's
  background-tab rendering throttling, even after the mitigating launch flags. Every immediate
  retry succeeds; the failure mode degrades gracefully to a placeholder image, never a crash.
- **Architectural**: cross-process Chrome/CDP tab management has no OS-level lock — two processes
  managing the same Chrome instance can collide and close each other's tabs. Currently mitigated
  only by operational discipline (don't run standalone diagnostic scripts against a Chrome
  instance a live process already owns).
- **Test coverage gaps**: watermark commands, tap-menu translation, the WeChat HTTP client, and
  the private-channel passcode flow are correct by manual trace but have no automated tests.
- No CI, no lint/format tooling wired up yet.
- `device-agent-mvp/`'s exposed API key remains unrotated (unrelated, disconnected prototype;
  human action item, not part of this release).
- No state-expiry for the equipment-selection flow; no dedicated duplicate-confirm UX; single
  retry only on WeChat send token-invalid errors — deliberate, pending product decisions.
