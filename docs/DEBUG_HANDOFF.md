# Debug Handoff — tab-not-debuggable / orphan-process incident

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
