# Handoff: WebStation browser session keep-alive/recovery

Session ended mid-investigation at user request. This document is the full handoff — no further code changes were made after this was written.

## 1. What this conversation accomplished

- Evaluated an external "Cookie 供应与保活" (cookie supply/keep-alive) microservice prompt template the user was considering handing to another coding agent. Determined the repo already has an equivalent, more appropriate mechanism (`CdpMultiTabService` + `BrowserProfileManager` — real Chrome session via CDP, not a cookie-serialization service) and recommended against building the proposed FastAPI/Redis/TTL microservice.
- User clarified the real complaint: the existing keep-alive only *pings* the backend; it never actively detects-and-fixes a truly dead session. Investigation confirmed this: `start_keep_alive()`'s background loop caught exceptions from `keep_alive()` but only logged them — nothing ever re-authenticated. Combined with `ensure_tab()` only ever calling `login()` once per tab per process lifetime, a session that died once stayed dead until a process restart.
- Implemented an MVP fix (see §2) adding an automatic re-login recovery path.
- Ran four live soak tests against the real production device (`10.121.0.14`, real `WEBSTATION_USERNAME`/`WEBSTATION_PASSWORD` credentials) to validate the fix under real session death, not simulated failure. Found and fixed a real detection gap along the way (see §2/§5).
- While this was in progress, **a second, related fix landed in the same file from an external source** (user or another agent/linter — instructed to treat as intentional): a per-tab `_tab_locks` / `_lock_for()` serialization mechanism, addressing a *different but related* real incident (a scheduled `Page.reload()` colliding mid-flight with a `login()`/`keep_alive()` call and wedging the tab permanently). **This was never reconciled against my changes** — see §5, first risk.

## 2. What is actually in code (working tree only — nothing committed to git)

### `src/screenshot_bot/browser/cdp_multi_tab_service.py`

My changes:
- `start_keep_alive(self, name, interval_seconds=60, on_failure=None, **keep_alive_kwargs)` — on a `keep_alive()` exception, logs it and then (new) calls `on_failure(error)` if provided, itself wrapped in try/except so a failed recovery attempt doesn't kill the background thread.
- New method `navigate(self, name, url, timeout_seconds=10)` — forces a CDP `Page.navigate()` to a given URL. Added specifically so a recovery attempt can force a clean, current read of login state instead of trusting a possibly-stale DOM (a tab that's still showing old app content, not yet redirected, would otherwise be misread by `_wait_for_login_page_state()` as "already_authenticated").
- `keep_alive()` dead-session detection hardened: originally only checked for `"LOGGED_OUT"` in the ping's response body. Now also captures the tab's current `location.href` in the same ping and treats `"login.html" in url` as an additional, independent dead-session signal. This was added *after* soak test 1 showed the body-only check can silently miss a session that's already sitting on `login.html` (see §5).

External changes (not mine, landed mid-conversation, never fully reviewed by me):
- `_tab_locks` dict + `_tab_locks_guard` lock + `_lock_for(name)` method on `CdpMultiTabService.__init__` — intended to serialize every CDP-issuing method (screenshot/login/keep_alive/navigate/refresh/navigate_equipment) per tab, per its own docstring, to fix an observed real bug: a scheduled refresh landing mid-login/keep-alive tore down the tab's JS context and wedged it permanently.
- New method `navigate_equipment()` + `from .equipment_navigation import navigate_to_equipment_graphic` — unrelated equipment-graphic routing feature, part of a separate, parallel workstream (see the many untracked `equipment_*`/`menu*`/`message_router.py` files in git status).
- **I never got a full read of the file after these landed** (my one attempt was declined by the user immediately before this handoff was requested). I do not know whether my `navigate()` method or the `_recover` closure's `login()` call are wrapped in `_lock_for()`. This is the top-priority open item — see §5.

### `src/screenshot_bot/browser/profile_manager.py`

My changes only:
- Added `from screenshot_bot.runtime.console_log import log_line` import.
- In `_apply_login()`, added a `_recover(error)` closure: logs the failure, navigates the tab to `target.get("start_url")` (falling back to `app_url`), then calls `login()` again with the same credentials/kwargs. Passed as `on_failure=_recover` to `start_keep_alive(...)`.

Nothing else in the repo was touched by me. Every other modified/untracked file visible in `git status` (README variants, `ansible/*`, `scripts/Bot.ps1`, `wechat/*`, `workflow/*`, `equipment_*`, `menu*.py`, `message_router.py`, `config.json`, `ansible/_diag.yml`, etc.) is pre-existing or externally changed, not part of this work.

## 3. What was only discussed, never implemented

- The original from-scratch "Cookie 供应与保活" microservice (FastAPI/Flask + Redis + TTL + async lock) — evaluated and explicitly rejected as redundant with the existing CDP session model. Nothing from it was built. Treat the rejection as a considered decision if it comes up again, not an oversight.
- Adding a similar "landed back on `login.html`" check to `refresh()` as defense-in-depth — floated early, never implemented (the actual fix targeted `keep_alive()` instead).
- Whether a single transient/ambiguous exception from `keep_alive()` (not a confirmed dead-session signal) should really trigger a full forced re-login — flagged as a live hypothesis (§5) but no guardrail was designed or implemented.
- Whether/how to git-commit this work — I asked the user; never answered before the conversation moved on and then was cut short.

## 4. Decisions later reversed or reframed

- My working explanation for soak test 1's 47-minute stuck-dead episode, given to the user at the time, was "the body-only `LOGGED_OUT` check misses a session already on `login.html`." The URL-check fix based on that explanation *did* work (soak test 3 recovered in ~3 seconds). But soak test 2 (a clean, uneventful ~120-minute session with zero anomalies) retroactively cast doubt on test 1's *very first* failure ("timed out", not a `LOGGED_OUT` match) having been a genuine session death at all. A second, competing hypothesis emerged — a transient CDP error triggering an unnecessary and possibly destructive forced re-login (this site rejects a second login attempt while a session is already valid) — and was never resolved. **Both explanations may be partially correct; this was never disambiguated.**
- The externally-landed `_tab_locks` mechanism describes fixing a race that could independently explain test 1's stuck period (concurrent CDP calls tearing down a mid-flight login). This means my original root-cause explanation to the user may be incomplete or wrong in part — this was also never reconciled.

## 5. Risks that still exist

1. **[Highest priority, unverified]** `navigate()` (mine) and `profile_manager._recover()`'s `login()` call may not be wrapped in the new `_lock_for(name)` per-tab lock. If not, the recovery path can still race against a concurrent `screenshot()`/`keep_alive()` call on the same tab — potentially reproducing the exact wedging bug `_lock_for()` was built to prevent, just via a different call path. **First thing the next agent should check.**
2. **Unconfirmed root cause, no guardrail added**: `start_keep_alive`'s `on_failure` fires on *any* exception from `keep_alive()`, not just a confirmed dead-session signal. On a site that rejects a second login while one session is already valid, forcing `navigate()+login()` off a transient/ambiguous error could itself break a healthy session. Not fixed; not fully confirmed as what actually happened in test 1.
3. **Soak test 4's outcome is unknown.** A background-task-completion notification arrived for it but its log was never read before this handoff was requested. See file path below.
4. **Nothing has been committed to git.** All changes exist only in the working tree.
5. **Live production credentials** (`WEBSTATION_USERNAME`/`WEBSTATION_PASSWORD` in `secrets.local.ps1`, repo root, gitignored) were sourced into background PowerShell processes and used directly against the real device repeatedly. No rotation/cleanup was requested or performed.
6. **Possible orphaned Chrome process.** Per standing user instruction, no test Chrome instance was ever terminated by this agent. The port-9338 instance was manually closed by the user partway through. The port-9339 (test 4) instance's final state at the end of this conversation is unknown — it may still be running, holding a live authenticated session against the production device, using an isolated profile dir under the session temp scratchpad.
7. **Test scripts and logs are NOT in the repo.** They live under the OS-level, per-session temp scratchpad path (see §6) — this is very likely **not accessible in a new session**. If the next agent needs to re-verify or continue soak testing, the scripts described in this document will need to be recreated from the descriptions here, not just re-read from disk.

## 6. What the next agent must know / do first

1. **Read the full current `src/screenshot_bot/browser/cdp_multi_tab_service.py` before touching anything.** Reconcile three things that landed in the same file without being cross-reviewed: my `on_failure`/`navigate()`/URL-check changes, the externally-added `_tab_locks`/`_lock_for()` mechanism, and the unrelated `navigate_equipment()` addition. Specifically confirm whether `navigate()` and the recovery path in `profile_manager.py` acquire `_lock_for(name)` — if not, fix that before anything else.
2. **Never kill any `chrome.exe` process on this local machine**, under any circumstances — confirmed standing instruction, reiterated multiple times this session. If cleanup of leftover test Chrome instances is needed, ask the user first.
3. **Check whether a test Chrome instance is still running on port 9339** (or elsewhere) before starting new tests — it may still hold a live session.
4. **Do not revisit the from-scratch cookie-microservice idea** (FastAPI/Redis/TTL) — already evaluated and rejected in this conversation as redundant with the existing CDP session model.
5. **Nothing is committed.** If asked to commit, scope it carefully — the working tree also has substantial unrelated pending work (equipment catalog/menu/message-router feature, wechat changes, ansible changes) mixed in; don't blanket `git add -A`.
6. **Test artifacts referenced in this doc are session-scoped and likely gone.** All of the following lived under:
   `C:\Users\frank\AppData\Local\Temp\claude\C--Users-frank-screenshot-bot-modular\5fb783ad-8940-4762-9fb2-ad0d93c47b26\scratchpad\`
   - `mvp_recovery_test.py` — offline fake-service wiring test (Part A); written but never actually executed (user redirected to real-credential live testing before it ran).
   - `mvp_recovery_live_test.py` / `.log` — soak test 1 (3.5h, Chrome port 9338, real credentials, `refresh_interval_seconds` deliberately omitted). Result: real death at ~53 min (atypically early, possibly not a genuine expiry — see §4), stuck for 47 min, eventually self-recovered. This run motivated the `keep_alive()` URL-check fix.
   - `mvp_recovery_live_test_v2.py` / `.log` — soak test 2 (2h, same Chrome/port, reused already-dead tab). Result: clean ~120-minute session (matches the site's documented `hasTimeout: true, timeout: 120`), died right as the window closed — inconclusive on recovery speed, but confirms real session lifetime and casts doubt on test 1's early death being genuine.
   - `mvp_recovery_live_test_v3.py` / `.log` — soak test 3 (2.5h, same Chrome/port). Result: **PASS** — real death at ~108 min, detected via both signals (body `LOGGED_OUT` and URL `login.html`), recovered in ~3 seconds, stable for the remaining ~70 min. This is the clearest evidence the fix works when the death signal is unambiguous.
   - `mvp_recovery_live_test_v4.py` / `.log` — soak test 4 (2.5h, fresh Chrome port 9339, fresh profile — started after the user manually closed the port-9338 instance). Login and initial screenshot confirmed good at start. **Final result never read — check this log first if continuing this work.**
7. **Real device/target config for reference**: `config.json` target `"1"`–`"5"` (`webstation-test`, `https://10.121.0.14/`), `login.enabled: true`, `keep_alive_interval_seconds: 60`, `refresh_interval_seconds: 3600` in production (my soak tests intentionally ran without refresh to force real deaths — production itself should keep refresh enabled).
