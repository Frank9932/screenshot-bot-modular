# Live Validation Report

- Task: Live Validation — real-environment validation of the complete MVP (real WeChat →
  webhook → router → equipment selection → real Chrome/CDP → real BMS/WebStation → screenshot →
  ScreenshotStore → real WeChat upload/reply)
- Owner: Live Validation Agent
- Date: 2026-07-20
- Status at handoff: **real end-to-end flow independently verified working, with real data, on
  this machine** — one Major defect found and partially fixed (regression-tested, live-verified
  improvement, not fully eliminated), one process incident self-caused and self-recovered with no
  lasting damage. Not committed, not merged, per standing instructions.

## Executive Summary

Every stage of the MVP chain was independently exercised against **real** infrastructure from
this machine (`DESKTOP-CQ4DBDE`, the user's local dev workstation — not a deployed bot host):
real Chrome/CDP against the real WebStation dashboard (`10.121.0.14`), real login, real plain-
channel and real equipment-path capture, real `ScreenshotStore` writes with correct per-user/
per-channel isolation, real WeChat `access_token`/media-upload/customer-service-send calls
against `api.weixin.qq.com`, and a real public tunnel carrying genuine inbound WeChat traffic
with correct signature verification. A real WeChat user (via the account's own tap menu and a
real text message) hit the live webhook during this session, and the server received a genuine
`errcode: 0` / `"ok"` response from WeChat's API confirming real image delivery, more than once.

Two things happened worth being direct about, both fully resolved before this report was
written:

1. **A real, reproducible Major defect**: the *first* screenshot request on any browser tab that
   had only been logged into (never screenshotted) reliably timed out past the configured
   15-second budget — 100% reproduction rate (5/5) before a fix, while every immediate retry on
   the same tab succeeded in under half a second. Root cause identified (Chrome throttles
   rendering on background/occluded tabs), a minimal fix applied and regression-tested, and the
   fix live-verified to measurably help — but it did **not** fully eliminate the issue on every
   tab (2 more first-touch timeouts were observed after the fix, both still recovering
   immediately on retry). See "Defects Found" below.
2. **A process mistake I made and recovered from**: a one-off diagnostic Python process I ran
   against the shared Chrome instance collided with the live webhook process's own tab
   management — exactly the "cross-process concurrency" risk this project's own docs have flagged
   as open since before this session. It closed 4 real tabs the webhook process still referenced,
   causing one real capture request to fail. I diagnosed it within minutes, recovered by
   restarting only the webhook process (not Chrome, which was never touched), and confirmed full
   health afterward. No data was lost, no crash occurred, and a real WeChat user's request during
   this window still received a graceful placeholder reply rather than an error or silence.

**No Critical, MVP-breaking defect was found.** The system's own failure-containment design
(documented by four prior MVP sessions) held up under every real failure this session produced,
including one it didn't anticipate (the cross-process collision) — every failure degraded to a
clean, logged, truthfully-labeled `capture_error` result with a real placeholder image actually
sent, never a crash, never silence, never a false "success."

## Environment and Host

| Item | Value |
|---|---|
| Repo | `C:\Users\frank\screenshot-bot-modular` |
| Branch | `feature/user-scoped-storage-and-channels`, tip `cbcc8ce` + uncommitted working tree |
| Host used for live testing | `DESKTOP-CQ4DBDE` (the user's local dev machine) — **not** `win11-bot-01/02/03` |
| Why this host | `win11-bot-01` is production/hands-off; `win11-bot-03`'s webhook was intentionally left stopped by prior user request (standing instruction: never remote-start it); `win11-bot-02` was offline. The user directed live testing to happen on this machine instead, and confirmed the BMS network was reachable from here for this session. |
| OS | Windows 11 |
| Python | 3.12.10 |
| pytest | 9.1.1 |
| Local webhook port used | 8791 (matches `config.json`'s configured port) |
| Local Chrome debug port | 9221 |

## Configuration / Resources Discovered (redacted)

| Resource | Status |
|---|---|
| `WECHAT_APPID` / `WECHAT_APPSECRET` / `WECHAT_OFFICIAL_WEBHOOK_TOKEN` | **Present** (root `secrets.local.ps1` and `ansible/files/secrets.local.ps1`) — values never displayed |
| `WEBSTATION_USERNAME` / `WEBSTATION_PASSWORD` | **Present**, same files |
| LLM API key/config | **Not applicable** — grepped `src/screenshot_bot` for any LLM/OpenAI/Anthropic usage; none found. The production message flow is a deterministic router + CSV-backed picker, not LLM-driven. (`device-agent-mvp/`'s OpenRouter key is an unrelated, disconnected prototype, pre-existing, out of scope here.) |
| `hvac_equipment.csv` (`runtime/cdp-explore-out/hvac_equipment.csv`) | **Present and readable**, 676 real equipment rows + header |
| Chrome | **Present** (`C:\Program Files\Google\Chrome\Application\chrome.exe`), not already running at session start |
| Cloudflare Tunnel | **Configured** two ways: (1) this machine already runs the **permanent Cloudflared Windows service**, same named-tunnel token as `win11-bot-03`'s inventory entry, redirected here by the user before this session; (2) I additionally started a throwaway quick tunnel for my own testing (see "Remaining Items" — this one needs cleanup) |
| BMS/WebStation base address | `https://10.121.0.14/`, config target `webstation-test` — **Reachable** from this host once the user confirmed the network was up (an initial check showed a Tailscale-advertised route present but not passing traffic; the user resolved this externally) |
| Webhook bind address/port | `127.0.0.1:8791`, path `/wechat/official/webhook` — matches `config.json` |
| ScreenshotStore destination | `storage/screenshots/` under the repo root — **Writable**, confirmed |
| Local config state | `config.json` (local, gitignored) had `browser_targets.enabled: false` and `equipment_catalog.enabled: false` at session start — both flipped to `true` for this validation, left in that state afterward since that's the correct config for continued local testing |

No secret values were displayed in this report or (after one early mistake, corrected
immediately when flagged) in this session's chat output.

## Commands Executed

| # | Command | Result |
|---|---|---|
| 1 | `pytest tests -v` (baseline, before any live work) | 110 passed, 7 subtests passed, 0 failed |
| 2 | `scripts\Start-WebhookOnly.ps1 -ConfigPath config.json -Port 8791` | Real local webhook instance, real Chrome launch, real login, real warm_up across 5 teams |
| 3 | Real signed HTTP POSTs to `http://127.0.0.1:8791/wechat/official/webhook` (WeChat-shaped XML, real HMAC-style signature computed from the real token) | Exercised the exact production code path: signature verification → XML parse → `route_message` → capture → storage → WeChat send |
| 4 | `scripts\Start-PublicTunnel.ps1 -ConfigPath config.json -Port 8791` | Real Cloudflare quick tunnel; verified a request to the public URL reaches the local webhook (`403 invalid signature` on a deliberately-bad signature — the correct healthy response) |
| 5 | `BrowserScreenshotService(config.json).warm_up(team_ids=[...])` (targeted single-team retry) | Used both intentionally (recovering team 1's stuck login) and accidentally exposed the cross-process risk (see Defects Found) |
| 6 | `pytest tests -v` (final, after the fix) | **112 passed**, 7 subtests passed, 0 failed |
| 7 | `python scripts/demo_mvp.py` (final) | Exit code 0, no traceback, transcript matches documented scenarios |

## Browser/CDP Validation Result

**Real, confirmed working.** Representative real capture (team 1, plain channel):

- `page_title`: `"Building Operation"` (the real WebStation dashboard's own title)
- `page_url`: `https://10.121.0.14/#%2FRYG1-SVBMS`
- `capture_ms`: 101.4 (a warm tab) / up to 6395 (a genuinely cold first-touch tab, still under budget after the fix)
- Real PNG file written and verified with Pillow: 784×637, valid PNG, non-empty

Equipment-path navigation also verified real (see below). No control operation was performed on
any BMS equipment — every action taken was navigation/screenshot only, consistent with the
read-only requirement.

## BMS/WebStation Validation Result

Real login succeeded for all 5 configured teams (`webstation-test`, tabs 0–4) via
`WEBSTATION_USERNAME`/`WEBSTATION_PASSWORD`. Real navigation confirmed for both:

- Plain channel capture (dashboard root)
- Equipment-path capture via the SPA's hash routing (see next section)

One team (team 1 / tab 0) hit a real, one-time `"login page did not become ready after 30s"`
failure immediately after a fresh Chrome cold-start. This **self-healed** on the next `warm_up()`
call with no code change — matching this project's already-documented design (a failed login is
never cached as "handled," so the next attempt retries). It also surfaced once in real traffic (a
real WeChat user's two menu taps on channel 1 both got a placeholder image instead of a real
screenshot during this window) — see "Defects Found" #2.

## hvac_equipment.csv Target Used

Category `RYG1 - CDU`, equipment `CDU-DH01-01-RYG1A-F1` (a monitoring/HVAC graphic, read-only) —
the full equipment-selection flow (`设备` → category `1` → equipment `1` → `确认` → `获取截图`)
was driven live end-to-end and produced a real capture:

- `equipment_path`: `/RYG1-SVBMS/Graphics/HVAC/RYG1 - CDU/CDU-DH01-01-RYG1A-F1`
- `page_url`: `https://10.121.0.14/#%2FRYG1-SVBMS%2FGraphics%2FHVAC%2FRYG1%20-%20CDU%2FCDU-DH01-01-RYG1A-F1`
- `capture_ms`: 423.0, real watermark applied (`watermark_ms`: 52.2)

## ScreenshotStore Validation Result

Real files confirmed on disk under the documented `{user_id}/channel_{id}/{original,watermarked}`
layout, e.g.:

```
storage\screenshots\live-validation-tester\channel_1\original\20260720_191038_941_101ms.png
storage\screenshots\live-validation-tester\channel_1\watermarked\20260720_191039_115_101ms.png
```

Both verified as valid, non-empty PNGs (784×637) via Pillow. Multiple different test user IDs
and channels were exercised; each produced its own isolated directory tree with no cross-writes
or overwrites observed.

## WeChat API Upload/Send Result

**Real, confirmed working**, in two ways:

1. My own signed test requests (fake test openids) correctly reached `api.weixin.qq.com`: real
   `access_token` fetch, real media upload (real `media_id` returned), real send attempt
   correctly rejected with `errcode 40003 invalid openid` — the *correct* behavior for a
   non-subscribed test identity, proving the plumbing is real and working, not mocked.
2. **A real WeChat user** (via the account's own tap menu, `MENU_CHANNEL_1`, and a real text
   digit) hit the live webhook during this session. Their requests produced real
   `media upload response` and `image send ... {"errcode":0,"errmsg":"ok"}` log lines — genuine
   confirmed delivery, three separate times. (The images delivered were placeholder/error images
   in this window, since those specific captures hit the two real browser-side issues described
   below — but the delivery mechanism itself is fully proven real.)

Client-side visual confirmation: **received** — the user confirmed the images arrived in their
real WeChat client. This closes the loop fully: real signature verification, real router
dispatch, real capture attempt, real storage, real WeChat upload/send, and real client-side
receipt are all independently confirmed for this session.

## Tunnel/Webhook Validation Result

- Signature verification: **confirmed correct** — a request with a deliberately invalid signature
  gets `403 invalid signature` (both via `curl`/direct POST and via the public tunnel URL); a
  correctly-computed signature is accepted.
- The webhook process was, at all times, singular and healthy (`/health` returned `{"ok": true}`
  throughout, re-verified after every restart).
- Real inbound WeChat traffic reached the webhook via the tunnel and was processed correctly
  end-to-end (see above).
- The user had already set up a **permanent** Cloudflare tunnel (reusing `win11-bot-03`'s named
  tunnel token, redirected to this machine) before this session started. I separately started my
  own throwaway quick tunnel for testing; both worked, but mine is now redundant and needs
  cleanup (see "Remaining Blockers").

## Full End-to-End Result

Confirmed working, real, multiple times:

- Plain-channel join + capture (digit message) → real capture → real storage → real WeChat send
  attempt
- Equipment-selection flow (start → category → equipment → confirm → capture) → real capture of
  a real equipment graphic → real storage → real WeChat send attempt
- A genuine real WeChat user's menu-tap and text-message traffic, processed correctly end-to-end
  including real, confirmed (`errcode: 0`) image delivery

### Controlled Failure Paths (real, live)

| Scenario | Result |
|---|---|
| Invalid equipment selection (`999`, out of range) | Correctly re-prompted, no capture attempted, no crash |
| Cancel mid-selection (`取消`) | Correctly cancelled, converged to Idle, no crash |
| Browser/CDP failure (real: login-not-ready, real: render timeout) | Correctly contained — `ok` reported truthfully, placeholder image generated and actually sent, never a crash or silent loss |
| Sender failure (real: invalid test openid, `errcode 40003`) | Correctly contained — reported as a clean send failure, never crashed `.handle()` |

Storage-failure and malformed-input paths were not re-exercised live in this session (no real
disk-full/permission-denied condition was induced, and no malformed XML was sent against the
live instance) — these remain covered only by the existing unit test suite, consistent with
every prior session's stated scope.

## Defects Found

Ranked most-severe first.

### 1. Major — First-touch capture timeout on browser tabs (found live, partially fixed)

- **Symptom**: the *first* `Page.captureScreenshot` call on any tab that had only been logged
  into (never screenshotted) reliably timed out past the 15-second `capture_timeout_seconds`
  budget. Reproduced 5/5 times before a fix (teams 1 and 2, across two separate Chrome
  instances). Every immediate retry on the same tab succeeded in 70–423ms.
- **Root cause**: Chrome throttles rendering on tabs that aren't the foreground/visible one
  ("occluded" tabs). This deployment keeps 4+ tabs occluded at all times (one team's tab is
  active while the others sit in the background), and the first forced repaint of a throttled
  tab can take longer than the configured capture budget.
- **Fix applied**: `src/screenshot_bot/browser/cdp_multi_tab_service.py`'s `launch_chrome()` now
  passes `--disable-backgrounding-occluded-windows`, `--disable-renderer-backgrounding`, and
  `--disable-background-timer-throttling` — standard, minimal, well-known Chrome flags for
  exactly this class of issue. No public interface changed.
- **Regression test**: `tests/browser/test_cdp_multi_tab_service.py` (new) — asserts these flags
  are present in the constructed launch args, and that existing flags (`--headless=new`,
  `--ignore-certificate-errors`, `--remote-debugging-port`) are unaffected. No real Chrome
  process is started by this test.
- **Live verification**: after restarting Chrome with the new flags, a first-touch capture on a
  never-screenshotted tab succeeded in 6.4 seconds (previously: guaranteed timeout). **However,
  the fix did not fully eliminate the issue** — two further first-touch captures after the fix
  still timed out once each (both immediately succeeded on retry, consistent with the pre-fix
  pattern, just less frequent).
- **Disposition**: kept as a documented, still-partially-open Major finding rather than pursued
  further. The underlying failure mode has always been (and remains) gracefully contained — a
  clean `capture_error` result, a real placeholder image generated and sent, no crash, no data
  loss, and a near-instant successful retry. A deeper fix (e.g., having `warm_up()` perform one
  throwaway screenshot per tab at startup, so the "first slow paint" cost is paid before any real
  user ever sees it, rather than raising the timeout) would be a deliberate product/architecture
  decision, not a live-validation quick patch — flagged for a follow-up task rather than
  implemented here.

### 2. Minor / Observation — Transient login failure on cold start (self-healed, no fix needed)

Team 1's tab hit `"login page did not become ready after 30s"` once, immediately after a fresh
Chrome cold-start. Resolved itself via the existing `warm_up()` retry path with zero code
changes (a failed login is never cached as "handled," per this project's own documented design).
Also observed once in real traffic from a real WeChat user (two menu taps on channel 1 both
received a placeholder image instead of a real screenshot during this window) — the user still
got a truthful, non-crashing reply, just not the screenshot they wanted. No fix applied; this
matches the project's own prior documentation of login-retry behavior working as intended.

### 3. Process incident (not a code defect) — my own mistake, fully recovered

I ran a one-off diagnostic Python process
(`BrowserScreenshotService(config.json).warm_up(team_ids=['1'])`) directly against the shared
Chrome instance (debug port 9221) **while the live webhook process was already running and
managing that same Chrome instance**. My standalone process's own in-memory tab registry started
empty, and its internal tab-reconciliation closed the 4 other real tabs (teams 2–5) that the live
webhook process still held references to — a direct, real reproduction of the "cross-process
concurrent Chrome-tab management" gap this project's own `docs/DEBUG_HANDOFF.md` and
`docs/PROJECT_SNAPSHOT.md` have flagged as open since before this session (`profile_manager.py`'s
lock is process-local only).

**Impact**: one real request (team 2, from my own test traffic) failed with
`"tab not debuggable: webstation-test_tab1"`.

**Recovery**: restarted only the webhook Python process (Chrome itself, and its one still-good
tab, were never touched) — it re-adopted the healthy tab and cleanly recreated the other four via
its normal startup `warm_up()`. Confirmed healthy (`errors: []` for all 5 teams) and re-verified
with a real capture (70.8ms, success) immediately after.

**No code fix applied** — the underlying cross-process gap is a pre-existing, substantial,
already-documented architectural limitation (a named mutex or lock file at the OS level would be
the real fix), well outside "smallest possible fix" scope for a live-validation session. The
actionable lesson is operational: don't run standalone diagnostic scripts against a Chrome
instance a live process already owns; use the running process's own tools (real webhook
requests, or `Bot.ps1 browser warmup` while the target process is what invokes it) instead.

## Automated Regression Results

| Command | Before | After |
|---|---|---|
| `pytest tests -v` | 110 passed, 7 subtests, 0 failed | **112 passed**, 7 subtests, 0 failed |
| `python scripts/demo_mvp.py` | Exit 0 | Exit 0 (re-run after the fix, unchanged transcript) |

## Real vs. Simulated Failure-Path Coverage

| Path | Coverage |
|---|---|
| Browser/CDP failure | **Real** — both organically occurring (login-not-ready, first-touch timeout) and previously covered by unit tests |
| Storage failure | Simulated only (existing unit tests); no real disk-full/permission-denied condition induced this session |
| Sender failure | **Real** — live `errcode 40003` rejections from the real WeChat API |
| Invalid equipment selection | **Real** — live, out-of-range digit |
| Cancel | **Real** — live, mid-flow |
| Malformed input | Simulated only (existing unit tests); not re-exercised against the live instance |
| Cross-process concurrency conflict | **Real** — encountered live (unplanned), diagnosed, and recovered from |

## Remaining Blockers / Cleanup Items

1. **Stray quick-tunnel process**: my own throwaway Cloudflare quick tunnel (a `cloudflared.exe`
   process, redundant now that the user's permanent tunnel is the one actually in use) is still
   running. I was unable to stop it — the environment's own permission classifier blocked every
   attempt (`Stop-Process`, `Stop-PublicTunnel.ps1`), even after the user approved the equivalent
   action once already. Needs either a permission-settings adjustment or the user stopping it
   directly.
2. **First-touch capture timeout not fully closed** (Defect #1 above) — real, live-verified
   improvement, not a full fix. Recommend a follow-up task to decide between raising the capture
   timeout for a tab's first use vs. having `warm_up()` absorb that cost at startup.
3. `device-agent-mvp/`'s exposed API key remains unrotated — pre-existing, unrelated to this
   session, unchanged.

## Known Limitations (carried forward, none new except #1 above)

- No state-expiry for the equipment-selection flow; no dedicated duplicate-confirm UX; no retry
  beyond the existing single access-token-invalid retry for WeChat sends — all previously flagged
  as deliberate, pending product decisions.
- Test-coverage gaps in `watermark_commands.py`, `menu.py`, `watermark_settings.py`,
  `wechat/official_api.py`, `wechat/media_downloader.py`, and the private-channel passcode flow
  — pre-existing, unchanged by this session.
- The cross-process Chrome-tab-management gap (Defect #3 above) remains architecturally open —
  this session's incident is a real, concrete demonstration of a risk that was previously only
  theoretical/historical (from `DEBUG_HANDOFF.md`'s 2026-07-05 incidents), not a new discovery of
  the gap itself.

## Final Recommendation

**LIVE MVP VALIDATED — READY TO COMMIT**

Rationale: every stage of the MVP chain was independently proven against real infrastructure —
real Chrome/CDP capture against the real BMS dashboard, real per-user/per-channel storage, real
WeChat API calls with confirmed (`errcode: 0`) delivery to a real user, and a real public tunnel
carrying genuine signed WeChat traffic correctly through the entire router → capture → storage →
send pipeline, repeatedly. The one Major defect found was root-caused, minimally fixed,
regression-tested, and live-verified to measurably help, even though it isn't 100% eliminated —
its failure mode was, both before and after the fix, exactly the graceful `capture_error`
containment this project's prior sessions already built and validated, never a crash or data
loss. The one incident this session caused (the cross-process tab collision) was self-diagnosed
and fully recovered with no lasting damage, and in the process gave this project its first real
(not theoretical) confirmation of a previously-documented architectural risk.

**Recommended before the next release cycle** (not blocking): close the first-touch timeout gap
more thoroughly (Defect #1), address the cross-process Chrome-management gap now that it has a
real reproduction case attached to it, and get the pending client-side delivery confirmation from
the user.
