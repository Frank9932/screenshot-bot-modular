# Debug Handoff

## Status as of 2026-07-20 (read this section first — supersedes 2026-07-17 below)

This update comes from a project-recovery pass over repo state only (git status/log,
code, docs) — not from a live debugging session, so it records *what exists*, not
*why* or *whether it's been tested/deployed*. Those are marked Unknown below rather
than guessed. See `docs/PROJECT_SNAPSHOT.md` for the full recovery writeup.

**The 2026-07-17 section below is now stale**: the working tree contains a further
wave of uncommitted, untracked work it does not mention at all —

- `src/screenshot_bot/workflow/menu.py` (untracked) — builds the WeChat custom
  tap-menu payload and translates a menu tap's `EventKey` back into the equivalent
  typed command text. Documented in `workflow/README.md` → "Tap menu".
- `src/screenshot_bot/wechat/menu_manager.py` (untracked) — `WeChatMenuManager`,
  pushes/reads the menu via `cgi-bin/menu/create`/`cgi-bin/menu/get`. Documented in
  `wechat/README.md`.
- `scripts/run_wechat_menu_sync.py` (untracked) — the `Bot.ps1 menu set`/`menu get`
  entrypoint.
- `src/screenshot_bot/workflow/equipment_catalog.py`,
  `equipment_prompts.py`, `equipment_selection_tracker.py` (all untracked) — a guided
  select-equipment flow (category → equipment → confirm → capture) gated behind
  `equipment_catalog.enabled` (default `false`). Documented in `workflow/README.md` →
  "Select-equipment flow" and `browser/README.md` → "Equipment navigation".
- `src/screenshot_bot/browser/equipment_navigation.py` (untracked) — the CDP-level
  hash-route navigation + pane-collapse this flow uses to show one equipment's own
  graphic before capturing.
- `scripts/screenshot_equipment_list.py`, `scripts/crawl_graphics_tree.py` (untracked)
  — offline tooling around the same equipment CSV (`category,equipment,path` columns)
  the select-equipment flow reads at `equipment_catalog.csv_path`.

**Unknown** (not recoverable from repo state alone — ask whoever did this work, or
check external session history if available): when this was built relative to
2026-07-17, whether it has been verified against a live WeChat account or only via
the module READMEs' manual test snippets, and whether it has been deployed to any of
bot-1/2/3.

**Current full uncommitted diff** (`git status`, superseding the list under
"Uncommitted changes (local, not yet committed on top of PR #4)" below, which is
missing everything listed above plus a few others):
```
M  README.md
M  ansible/README.md
M  ansible/deploy.yml
M  config.example.json
M  docs/DEBUG_HANDOFF.md
M  scripts/Bot.ps1
M  scripts/Start-WebhookBackground.ps1
M  scripts/Stop-WebhookBackground.ps1
M  src/screenshot_bot/browser/README.md
M  src/screenshot_bot/browser/cdp_multi_tab_service.py
M  src/screenshot_bot/browser/profile_manager.py
M  src/screenshot_bot/browser/screenshot_service.py
M  src/screenshot_bot/wechat/README.md
M  src/screenshot_bot/wechat/official_api.py
M  src/screenshot_bot/wechat/webhook_server.py
M  src/screenshot_bot/workflow/README.md
M  src/screenshot_bot/workflow/help_text.py
M  src/screenshot_bot/workflow/wechat_image_reply.py
?? ansible/tasks/tunnel.yml
?? config.json                                    <- local-only, intentionally never committed
?? device-agent-mvp/                               <- unrelated prototype, see PROJECT_SNAPSHOT.md
?? scripts/Watch-WebhookLog.ps1
?? scripts/crawl_graphics_tree.py
?? scripts/run_wechat_menu_sync.py
?? scripts/screenshot_equipment_list.py
?? src/screenshot_bot/browser/equipment_navigation.py
?? src/screenshot_bot/wechat/menu_manager.py
?? src/screenshot_bot/workflow/equipment_catalog.py
?? src/screenshot_bot/workflow/equipment_prompts.py
?? src/screenshot_bot/workflow/equipment_selection_tracker.py
?? src/screenshot_bot/workflow/menu.py
?? src/screenshot_bot/workflow/message_router.py
```
Per the same standing working agreement noted below: only commit/push when the user
explicitly asks.

**Also flagged during this recovery pass** (see `docs/PROJECT_SNAPSHOT.md` for
detail, not repeated here): `screenshot_store/README.md` had a stale key-format
example (now fixed); no automated test suite exists anywhere in this repo;
`device-agent-mvp/.env` appears to contain a live API key in plain text.

---

## Status as of 2026-07-17

**Branch**: `feature/user-scoped-storage-and-channels`, PR
[#4](https://github.com/Frank9932/screenshot-bot-modular/pull/4) open against `master`
(not merged). Local working tree has further uncommitted changes on top of that PR —
see "Uncommitted changes" below.

### What this branch adds, on top of the channel/watermark work in PR history
- **Storage reordered** to `{user_id}/channel_{id}/{original,watermarked}` (was
  `channel_{id}/{user_id}`) for both outgoing screenshots and incoming photos — a
  sender's own folder is now the top-level grouping, channel nested inside it.
- **`virtual_desktop`/desktop-screenshot capability removed entirely** (dead code path
  in practice — `capture_message_types` was always `"none"`, `virtual_desktop.enabled`
  always `false`). Capture dispatch is now just: channel digit/photo → browser capture,
  or a plain-language guidance reply for everything else.
- **Channel count is config-driven**, not hardcoded to 5. `browser_targets.targets` can
  hold any number of channels; the example config ships 5 regular + 3 "backup" channels
  (`"backup": true`) that work identically but are omitted from `帮助`/guidance text.
- **Private channel is now passcode-gated**: `私密`/`private` does nothing until a
  sender first sends the exact text `11223344` (`help_text.PRIVATE_CHANNEL_PASSCODE`),
  which unlocks it for them persistently (`UserTeamTracker.unlock_private`). The
  post-unlock confirmation text was later trimmed to not restate the trigger words.
- **First-join notice**: the first time a sender ever joins any channel, a follow-up
  text tells them their images are archived per-user.
- **Interaction layer decoupled**: new pure module
  [message_router.py](../src/screenshot_bot/workflow/message_router.py) —
  `route_message(...)` takes a message + the sender's already-looked-up state and
  returns a decision dict (`join_channel`, `recapture`, `guidance`, etc.) with zero I/O.
  `wechat_image_reply.py`'s `WeChatImageReplyWorkflow` is now a thin executor of those
  decisions. Runnable standalone for debugging: `python -m screenshot_bot.workflow.message_router`.
- **WeChat API per-call timing** (`token_ms`/`upload_ms`/`send_ms`) added to the JSONL
  event log — this is what originally diagnosed a slow-reply investigation on `win11-bot-02`
  (root cause turned out to be Hyper-V LSO on that VM's virtual NIC, since fixed).
- **`webhook_server.py`: `allow_reuse_address = False`** — the real fix for a
  recurring split-brain bug (see "Split-brain / duplicate webhook process" below,
  which connects to the *old* incident documented further down this file under
  "Incident 2/3").
- **Tunnel management overhauled**:
  - `Bot.ps1 tunnel permanent-install -TunnelToken <token>` installs cloudflared as a
    Windows service bound to a named Cloudflare Tunnel (stable hostname, survives
    reboots) — as opposed to the old throwaway quick tunnel.
  - Wired into `deploy.yml` by default via `ansible/tasks/tunnel.yml`: runs
    automatically whenever `bot_tunnel_token` is set for a host (host var in
    `inventory.yml`, gitignored/real file — bot-3's token is already there).
  - **`Bot.ps1 all kill`/`all restart` no longer touch any tunnel at all** (quick or
    permanent) — tunnel is managed independently as infrastructure now.
  - `Bot.ps1 status` shows both the permanent-tunnel service status and the quick-tunnel
    state separately (previously it only checked the quick-tunnel state file, which
    always read "not running" once a host switched to the permanent service).
- **New log watcher**: [scripts/Watch-WebhookLog.ps1](../scripts/Watch-WebhookLog.ps1) —
  colorized, one-line-per-event live tail of the JSONL log with safe/defensive JSON
  parsing and forced UTF-8 console output (fixes a real mojibake/`??` bug in how
  `Get-Content` reads the log without `-Encoding UTF8`, also fixed in the pre-existing
  `Invoke-WebhookLogs`). Launch via `Bot.ps1 webhook watch` — opens fully detached in
  its own new console window (`Start-Process`, no `-Wait`), parent returns in under 2s.

### Deployment state across hosts (as of this session)
- **`win11-bot-01`**: **production, user manages manually.** Do not deploy, restart,
  or touch its running process without being explicitly asked again — this instruction
  was given explicitly mid-session and still stands.
- **`win11-bot-02`**: not touched recently in this session; last known state was
  healthy after the LSO/ARP fixes from an earlier part of this session (see
  conversation history, not repeated here). Status not re-verified as of this handoff.
- **`win11-bot-03`**: this branch's code is deployed (`deploy.yml --skip-tags secrets`,
  secrets intentionally left alone since bot-3 already has its own working WeChat
  credentials distinct from bot-1/bot-2's). Permanent tunnel installed and verified
  reachable at `https://wechat-screenshot-1.hankarobotic.com/wechat/official/webhook`
  (a plain curl gets `403 invalid signature`, which is the *correct* healthy response —
  it means the request reached the webhook's own signature check). **Webhook/Chrome are
  currently NOT running on bot-3** — the user explicitly said "let me start the bot
  myself" after repeated failed remote-start attempts (see next section) and asked me
  to stop trying. Do not attempt to remotely start/restart the webhook on bot-3 unless
  asked again.

### Split-brain / duplicate webhook process — recurred this session, root cause still incomplete
This is the same *symptom* as the historical incident documented below (two processes
matching `run_wechat_official_webhook.py`, one via `.venv\Scripts\python.exe` and one via
a bare system `python.exe` under a different user profile, both bound to port 8791 at the
exact same creation timestamp), but it recurred on **both bot-1 and bot-3** during this
session through a *different* trigger than the original incident:

- On bot-1, the trigger was found and fixed: a **leftover scheduled task**
  (`ScreenshotBotModular-Webhook`, pointing at a legacy launcher script under
  `logs\run-webhook.ps1`, using a different Python interpreter) — created by an earlier
  deployment before `create_startup_task: false` became the default. Removed via
  `Unregister-ScheduledTask`; confirmed gone; a subsequent clean start showed no
  split-brain.
- On bot-3, the **same symptom reproduced multiple times even from a verified clean
  process-zero state**, and an exhaustive search found **no scheduled task, no Windows
  service, no startup-folder item, no WMI event subscription** responsible. It happened
  whether the `ansible-playbook bot.yml -e bot_command=webhook -e bot_action=start` call
  was run in the foreground, backgrounded via the harness, or even when the whole
  `Bot.ps1 webhook start` invocation was wrapped in its own detached `Start-Process` (which
  eliminated the split-brain but caused a *different* problem: the webhook died entirely
  once the WinRM session closed, because the extra process-nesting broke the detachment
  that normally lets `Start-WebhookBackground.ps1`'s child survive past the ansible task).
  **Working theory** (not confirmed): a WinRM/ansible transport-level double-execution of
  the long-blocking `win_shell` task against bot-3's Tailscale connection (independently
  observed to be flaky to this host throughout the session — repeated `tailscale status`
  "logged out"/coordination-server-unreachable events). This is *not* fixed at the code
  level — `allow_reuse_address = False` (see above) makes a genuine double-launch fail
  loudly instead of silently coexisting, which is a real improvement, but doesn't explain
  or prevent the double-launch itself. **Given this, and the user's explicit instruction
  to stop attempting remote starts on bot-3, this remains an open, unresolved
  infrastructure question** — if it recurs when the user starts it manually (not via
  ansible), that would be strong evidence the trigger is ansible/WinRM-specific, not a
  bug in `Start-WebhookBackground.ps1` itself.

### Unresolved: local test instance on this dev machine
Last action before this handoff was updated: attempted to start a local test instance
(`scripts/Start-WebhookOnly.ps1 -ConfigPath config.example.json -Port 8792`, launched
detached via `Start-Process`, intended to be paired with a quick tunnel redirected to
port 8792) to test against the existing tunnel tooling. A health check against
`http://127.0.0.1:8792/health` immediately after failed with "Unable to connect to the
remote server" — i.e. the process did not come up (or came up and exited) within the
few seconds waited. **Not yet diagnosed** — the investigation was interrupted before
checking the spawned window/process for an error. Local `config.json` has
`browser_targets.enabled: false` (no Chrome/browser testing intended for this local
run, just the WeChat message-handling/tunnel path), and `secrets.local.ps1` exists
locally with real credentials sourced by `Start-WebhookOnly.ps1`. Next step for whoever
picks this up: re-run `Start-WebhookOnly.ps1 -Port 8792` directly in a foreground
console (not detached) to see its actual startup error output, since the detached
window's output was never captured/inspected.

### Known gotchas hit again this session (still apply)
- **Apostrophes in `win_shell` comments break Ansible's free-form argument parsing** —
  hit repeatedly across this whole project's history; reword to avoid apostrophes.
- **PowerShell `2>&1` on a native executable's stderr, combined with
  `$ErrorActionPreference = "Stop"`, turns routine stderr chatter into a terminating
  error** — hit with `cloudflared.exe`'s own INFO-level log lines during
  `tunnel permanent-install`, which logs to stderr as a matter of course, not as an
  error signal. Fixed by locally scoping `$ErrorActionPreference = "Continue"` around
  just those two calls in `Invoke-TunnelPermanentInstall` (see `scripts/Bot.ps1`).
- **`Get-Content` without `-Encoding UTF8` misreads this project's UTF-8 log files on
  Windows PowerShell 5.1**, producing mojibake or `??` for Chinese content depending on
  the system's console codepage — fixed in `Invoke-WebhookLogs` and
  `Watch-WebhookLog.ps1`; also needed `[Console]::OutputEncoding = UTF8` explicitly for
  correct *display*, since the encoding and console-output problems are separate issues
  that both need fixing (confirmed via `Start-Job`/`Receive-Job` testing being an
  unreliable way to verify console encoding — it adds its own serialization layer; use
  `Start-Process -RedirectStandardOutput` for a faithful test instead).

### Uncommitted changes (local, not yet committed on top of PR #4)
```
M  ansible/README.md
M  ansible/deploy.yml
M  scripts/Bot.ps1
M  src/screenshot_bot/workflow/README.md
M  src/screenshot_bot/workflow/help_text.py
M  src/screenshot_bot/workflow/wechat_image_reply.py
?? ansible/tasks/tunnel.yml
?? config.json                                    <- local-only, intentionally never committed
?? scripts/Watch-WebhookLog.ps1
?? src/screenshot_bot/workflow/message_router.py
```
Per this project's standing working agreement: only commit/push when the user
explicitly asks, even though bot-3 already has all of this deployed.

### Suggested next steps for whoever picks this up
1. Diagnose the local test-instance failure (port 8792) — rerun
   `Start-WebhookOnly.ps1` in the foreground to see the actual error.
2. Once local testing works, the original ask was: start a quick tunnel
   (`Start-PublicTunnel.ps1 -Port 8792`) redirected at the local instance, to test the
   webhook end-to-end without needing a remote host.
3. If/when the user wants bot-3's webhook started, that is explicitly theirs to do —
   do not attempt it via ansible again without being asked, given the unresolved
   split-brain question above.
4. Ask the user whether to commit the currently-uncommitted changes listed above
   (do not do this proactively).
5. Bot-2's status hasn't been re-checked in a while — worth a status pass if it comes
   up again.

---

# Historical: tab-not-debuggable / orphan-process incident (2026-07-05, resolved)

Status as of 2026-07-05 (updated, ~03:59 UTC): **the ansible-restart fix from earlier
today is verified correct for its own trigger path, but a THIRD incident was found live
on `win11-bot-01` during follow-up verification — a different trigger reproduces the
same orphan-doubling symptom.** See "Incident 3" below. Changes below are **not
committed** yet (only deployed to the remote host's working tree via
`ansible-playbook deploy.yml`).

## Environment

- Primary test/deploy target: `win11-bot-01` (100.97.205.111), Ansible inventory group
  `screenshot_bot_modular`, install dir `C:\Tools\screenshot-bot-modular`.
- Do **not** touch `win11-golden-test-01` unless explicitly asked — it's a separate host,
  not currently in scope.
- Ansible controller runs from WSL: `wsl -d AnsibleUbuntu -- bash -lc "cd /mnt/c/Users/frank/screenshot-bot-modular/ansible && ansible-playbook ..."`.
- Live login-gated site under test: Schneider Electric EcoStruxure Building Operation
  WebStation at `10.121.0.14`, config target name `webstation-test`; credentials are in
  the Ansible inventory/group_vars, not repeated here.
- Team mapping: WeChat team ids `1`-`5` each map to one tab (`webstation-test`,
  `webstation-test_tab1..tab4`) of the *same* shared WebStation login session.
- Current public tunnel (Cloudflare quick tunnel): `https://therefore-telescope-police-invalid.trycloudflare.com`
  — already pasted into the WeChat console; unchanged across the latest restart, so no
  action needed there unless it's rotated again.

## The incident chain (chronological)

1. **First report**: "chrome 重启后 错误显示 tab not debuggable" (after Chrome restart,
   error shows tab not debuggable).
   - First fix attempt: added a `threading.Lock()` around `ensure_tab()` in
     [profile_manager.py](../src/screenshot_bot/browser/profile_manager.py) to close a
     TOCTOU race between `warm_up()`'s background thread and a concurrent real capture
     request (both could interleave during `add_tab()`'s blocking HTTP call because the
     GIL releases during I/O, letting `close_untracked_tabs()` on one thread close a tab
     another thread just created but hadn't registered yet).
   - Also hardened `_get_page()` in
     [cdp_multi_tab_service.py](../src/screenshot_bot/browser/cdp_multi_tab_service.py)
     to retry for up to 3s (polling every 200ms) instead of failing immediately, since a
     freshly-created tab's devtools target can take a brief moment to expose
     `webSocketDebuggerUrl` on the very first `/json/list` call.
   - Deployed. Locally reproduced the race with a mock login site + concurrent
     `warm_up()` + 5 simultaneous captures — passed with the lock, but **also passed
     3/3 without the lock** against the local mock, meaning the mock (fast, localhost)
     could not reliably reproduce the real race window. This was disclosed honestly
     rather than claimed as proof.

2. **Second report**: "相同问题依然存在" (same problem still exists) — proof the above
   fix did not address the real recurrence pattern in production.
   - Deep investigation via direct WinRM commands against `win11-bot-01`:
     - `bot.yml -e bot_command=status` repeatedly showed **4** python processes
       matching `run_wechat_official_webhook.py` instead of the expected 2 — i.e. two
       full parent/child pairs from two different restart events coexisting.
     - Confirmed via `Get-CimInstance Win32_Process` + `GetOwner` that both pairs were
       legitimate venv-launcher parent/child structures, just from different restarts —
       one of them was an orphan nobody was tracking.
     - Confirmed `state.json`'s tracked `webhook_pid` only pointed at *one* of the two
       pairs; the port listener (`Get-NetTCPConnection -State Listen` on 8791) matched
       the tracked pair, so the orphan pair was silently running a second, forgotten
       instance of the whole browser/tab stack — colliding with the tracked instance
       over the same Chrome debug port / tabs, producing "tab not debuggable" noise.
     - Directly invoked `scripts/Stop-WebhookBackground.ps1` via a **plain WinRM shell
       session** (not through the scheduled task) and confirmed it killed **all 4**
       processes cleanly — proving the kill logic in that script is correct.
     - Root cause isolated to **`ansible/webhook-start.yml`**: it only manages the
       scheduled-task definition (`schtasks /End /Delete /Create /Run /IT`) and never
       explicitly called `Stop-WebhookBackground.ps1` in the WinRM session. It relied
       entirely on `Start-WebhookBackground.ps1`'s own internal stop call running
       *inside* the newly-scheduled task's `/IT` (interactive token) session — and a
       process in one session does not reliably terminate a process from a *different*
       session, even under the same user account. `schtasks /End /Delete` only removes
       the task definition, not a process it had already detached via `Start-Process`.
   - **Fix applied**: added an explicit
     `powershell.exe -File Stop-WebhookBackground.ps1` call in the WinRM session in
     [ansible/webhook-start.yml](../ansible/webhook-start.yml), placed after
     `schtasks /End /Delete` and before `schtasks /Create /Run`.
   - **Gotcha hit while editing**: the first version of the added comment included an
     apostrophe (`webhook_pid's`), which broke Ansible's `win_shell` free-form argument
     parsing (`Error loading tasks: failed at splitting arguments, either an unbalanced
     jinja2 block or quotes`). Rewrote the comment to avoid apostrophes/stray quotes.

## Verification performed (this session)

- Ran the fixed `webhook-start.yml` against `win11-bot-01` — succeeded, log showed
  `Webhook stopped.` executing before the new instance started, confirming the
  previously-missing stop call now actually runs.
- `bot.yml -e bot_command=status` afterward showed exactly **2** processes (20204
  parent, 16220 child) — the single legitimate pair, `local_health.ok: true`.
- Pulled `webhook logs` and confirmed the latest `browser_warm_up` entry (this boot)
  has `"errors": []` for all 5 teams/tabs — clean warm-up, no "tab not debuggable" on
  this boot.
- All prior "tab not debuggable" log entries are timestamped before this restart
  (03:22 UTC 2026-07-05) — i.e. leftover history from the orphan-process bug, not new
  occurrences after the fix.

## Incident 3 (found 2026-07-05, ~03:59 UTC, during follow-up verification)

While checking in on the fix per "suggested next steps" below, `bot.yml -e
bot_command=status` against `win11-bot-01` showed **4** webhook processes again —
the exact symptom Incident 2's fix targeted — despite the scheduled task having run
only **once** (`schtasks /Query /V` showed `Last Run Time` matching
`webhook-task.log`'s single write at 10:22:31 local).

- Pair A: `20204`/`16220`, started 10:22:31 local — this is the legitimate restart
  from Incident 2's verification, launched via the fixed `webhook-start.yml`.
- Pair B: `27080`/`13676`, started 10:28:05 local (6 minutes later) — **not launched
  by ansible or the scheduled task at all.** Its parent (`15872`) is a long-lived
  interactive `powershell.exe` console (alive since 2026-07-04 17:39, well before
  either restart), i.e. someone ran a start/restart command **by hand, directly on
  the box**, outside all the tooling this handoff has been fixing.
- `Get-NetTCPConnection -LocalPort 8791` shows the *actual* listener is `16220`
  (Pair A's child) — meaning `runtime\wechat-official-webhook-state.json` (tracking
  `27080`) is now pointing at the **wrong** process.
- Pair B's own `server.out.log` shows it ran a `browser_warm_up` with real errors —
  `"tab 0: login page did not become ready after 30s"` for teams 1-4, and one
  explicit `"keep_alive(webstation-test) failed: tab not debuggable: webstation-test"`
  — then, later in the same log, **successful** real WeChat traffic (`wechat image
  send response: {"errcode":0,"errmsg":"ok"}`). That mix is only consistent with
  both Pair A and Pair B being simultaneously live and answering on the same port
  (Windows can allow two listeners on one port via `SO_REUSEADDR`-like behavior, and
  `Get-NetTCPConnection` appears to only surface one entry) — i.e. a **split-brain**:
  two independent processes each running their own `BrowserProfileManager` /
  `CdpMultiTabService` against the *same* shared WebStation login session, racing
  each other over the same tabs. Whichever process happens to handle a given
  incoming webhook request determines whether it hits a tab the *other* process just
  touched.

**Why Incident 2's fix didn't prevent this**: `Start-WebhookBackground.ps1` always
self-stops previous instances first (calls `Stop-WebhookBackground.ps1`
unconditionally, regardless of how it's invoked), and that kill logic is verified
correct when run through WinRM/ansible (confirmed running at "High" mandatory
integrity level). But Pair A (`20204`) was launched by the scheduled task with
`/RL HIGHEST` (elevated). The leading theory is that the interactive console
(`15872`) was **not** "Run as Administrator" (Medium integrity), and Windows
silently blocks a lower-integrity process from terminating a higher-integrity one —
`Stop-Process -Force -ErrorAction SilentlyContinue` in
[Stop-WebhookBackground.ps1](../scripts/Stop-WebhookBackground.ps1) swallows that
access-denied failure instead of surfacing it, so the stop *looked* like it ran
cleanly but didn't actually kill anything. This has not been directly confirmed
(would need to check the console's token elevation), but it fits every observed
fact and matches known Windows UAC behavior for split admin tokens.

This also exposes a second, independent gap: the `threading.Lock()` added in
Incident 1's fix ([profile_manager.py](../src/screenshot_bot/browser/profile_manager.py))
is process-local. It does nothing to prevent two *separate* Python processes from
managing tabs on the same shared Chrome debug port concurrently, which is exactly
what happened here once Pair B failed to displace Pair A.

**Resolved (this session)**: with the user's explicit go-ahead, ran
`ansible-playbook webhook-restart.yml --limit win11-bot-01`. Ansible's WinRM session
runs at "High" mandatory integrity, so it was able to kill both pairs cleanly. Result:
- Fresh single pair `3112`/`19220`, `local_health.ok: true`.
- `bot.yml -e bot_command=status` process_ids now shows exactly **2** PIDs, matching
  the tracked `webhook_pid` (3112).
- Fresh `browser_warm_up` shows `"errors": []` for all 5 teams/tabs — no
  "tab not debuggable", no login-timeout, clean across the board.

This confirms the restart-collapse works when triggered through ansible (as
expected, since that path is elevated). It does **not** fix the underlying trigger
(a non-elevated manual start silently failing to displace an elevated one) or the
cross-process gap — those are still open, see suggested next steps below. If the
same interactive console runs another start/restart by hand, this can recur.

## Incident 3 root-cause fix (this session, after the above)

User confirmed the trigger: they manually ran a browser restart from their own
interactive console on `win11-bot-01` (i.e. `Bot.ps1 browser restart` /
`Bot.ps1 webhook restart` run by hand, not through ansible). Two fixes applied:

1. **Removed `/RL HIGHEST` from all three scheduled-task creations** —
   [ansible/webhook-start.yml](../ansible/webhook-start.yml),
   [ansible/webhook-restart.yml](../ansible/webhook-restart.yml), and
   [ansible/tasks/startup.yml](../ansible/tasks/startup.yml) (the optional logon
   task, currently disabled via `create_startup_task: false` but fixed for
   consistency). Nothing the webhook launches needs elevation; running it at the
   same integrity level as a normal interactive console removes the Windows
   security boundary that let a non-elevated `Stop-Process` call silently fail
   against an elevated target.
2. **Made a stop failure loud instead of silent** — in
   [Stop-WebhookBackground.ps1](../scripts/Stop-WebhookBackground.ps1), the final
   check after 5 kill attempts now `throw`s (naming the surviving PIDs and
   suggesting re-running elevated) instead of just `Write-Warning`, so
   `Start-WebhookBackground.ps1` will hard-fail rather than silently proceeding to
   start a second, colliding instance if a future stop ever fails for any reason.

**Gotcha hit again while editing**: two of the three new comments originally
contained apostrophes (`task's process`, `can't kill`) and broke `win_shell`
free-form parsing the same way as the Incident 2 fix did — same lesson, still
applies. Caught before deploying, reworded to avoid apostrophes.

**Verified**: deployed the changed `scripts/` directory to `win11-bot-01`
(`ansible-playbook deploy.yml --tags app`), then ran `webhook-restart.yml` again —
clean single pair (`14296`/`4284`), `local_health.ok: true`, `browser_warm_up`
`"errors": []` for all 5 teams/tabs, and `schtasks /Query /V` on the recreated task
shows no elevation requested.

**Still not proven**: a real non-elevated manual restart hasn't been re-tried since
this fix (all verification here was via the elevated ansible/WinRM path, which was
never the failing case). Next time you manually restart the browser/webhook from
your own console, that's the real test — if it now cleanly kills the previous
instance instead of doubling up, this is fully closed.

## What is NOT yet verified

- **No real live WeChat message has hit the webhook since this restart.** The
  verification above only proves the *restart path* is clean (no orphan processes, no
  warm_up errors). It does not yet prove a real incoming message/capture request
  avoids "tab not debuggable" end-to-end. Next real message should be watched via
  `bot.yml -e "bot_command=webhook bot_action=logs"` for any `capture_error` fields.
- No additional restart cycles have been exercised beyond this one — if you want higher
  confidence, run `ansible-playbook webhook-restart.yml --limit win11-bot-01` a couple
  more times and confirm process count stays at 2 each time.

## Uncommitted changes (all local, not pushed)

```
M  README.md
M  ansible/README.md
M  ansible/webhook-start.yml            <- the fix described above
M  docs/ARCHITECTURE.md
M  scripts/Start-WebhookBackground.ps1  <- calls Stop-WebhookBackground.ps1 internally
M  scripts/Stop-WebhookBackground.ps1   <- retry-and-verify loop, kills ALL matching PIDs
M  src/screenshot_bot/browser/cdp_multi_tab_service.py  <- _get_page() retry
M  src/screenshot_bot/browser/profile_manager.py        <- ensure_tab() lock
?? ansible/bot.yml                      <- thin wrapper for scripts/Bot.ps1
?? ansible/tunnel-start.yml
?? ansible/tunnel-status.yml
?? ansible/tunnel-stop.yml
?? ansible/webhook-restart.yml
?? scripts/Bot.ps1                      <- unified CLI entry point (status/webhook/browser/tunnel)
?? scripts/Start-PublicTunnel.ps1       <- Cloudflare quick tunnel w/ USERPROFILE isolation
?? scripts/Stop-PublicTunnel.ps1
```

These have all been deployed to `win11-bot-01` via `deploy.yml --tags app`, but are
**not committed to git**. An earlier, separate batch of work (the initial
`CdpMultiTabService` integration) was already committed and merged as
[PR #1](https://github.com/Frank9932/screenshot-bot-modular/pull/1) — this handoff
covers everything *after* that PR.

Per established working agreement in this project: only commit/push when the user
explicitly asks, even though the changes above are already deployed and verified.

## Known prior incidents (context, already resolved)

- **Stale tunnel URL caused "no reply"**: account `oerGt3IRCp6LagUl5ZkRRTIUVuaM` sent
  messages and got no reply because the tunnel had been restarted while building
  tooling without clearly flagging the URL change as action-required. Resolved by
  re-pasting the fresh URL into the WeChat console. Lesson: always call out tunnel URL
  changes explicitly and loudly.
- **Wrong-process-killed outage**: an early diagnostic cleanup script
  (`kill_orphan_pair2.ps1`) had inverted parent/child keep-logic and killed the
  legitimate port listener instead of the orphan, causing a real outage. Fixed
  immediately via `webhook-start.yml`. Lesson: when writing one-off diagnostic kill
  scripts, verify the "keep" set against the actual port listener
  (`Get-NetTCPConnection`), not just the tracked PID's ancestry.
- **Cloudflare quick tunnel 404s**: caused by a pre-existing named-tunnel
  `~/.cloudflared/config.yml` on `win11-bot-01` hijacking `--url` (quick tunnel)
  requests. Fixed by overriding `USERPROFILE` to an isolated directory during
  `Start-Process` in `Start-PublicTunnel.ps1`.

## Suggested next steps for whoever picks this up

1. **Urgent**: decide with the user how to clean up the current split-brain on
   `win11-bot-01` (Pair A `20204`/`16220` vs Pair B `27080`/`13676` — see Incident 3).
   Given the "wrong-process-killed outage" lesson, verify against the actual port
   listener (`Get-NetTCPConnection -LocalPort 8791`) again immediately before killing
   anything, since either pair could in principle have taken over the port by the
   time this is picked up. Simplest safe path is probably a full `webhook-restart.yml`
   run (ansible's WinRM session is confirmed to run at "High" elevation, so it can
   kill both pairs), which produces one clean tracked instance — but confirm with the
   user first since it's a live bot and will briefly interrupt service.
2. Ask whoever has access to `win11-bot-01`'s desktop/RDP session whether they (or an
   unattended script) ran a webhook start/restart command by hand around 2026-07-05
   10:28 local time — that's the actual trigger for Incident 3, and it'll recur unless
   whatever ran it either goes through the ansible path or gets fixed to run elevated.
3. Consider a code-level follow-up: `Stop-WebhookBackground.ps1` should surface (not
   silently swallow) an access-denied failure when it can't kill a tracked/matching
   process, so a future non-elevated manual start fails loudly instead of quietly
   doubling up. A cross-process guard (e.g. a named mutex or lock file checked by
   `run_wechat_official_webhook.py` at startup) would close the gap that Incident 1's
   `threading.Lock()` can't cover, since that lock is process-local.
4. Once Incident 3 is resolved and re-verified clean, resume the original plan: watch
   the log after the next real WeChat message for `capture_error`, optionally run
   `webhook-restart.yml` a couple more times for confidence, then ask the user whether
   to commit this batch of changes and open a follow-up PR (do not do this
   proactively).
