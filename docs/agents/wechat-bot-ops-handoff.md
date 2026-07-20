# Handoff: WeChat tap-menu/equipment-flow feature + bot-3 ops session

Branch: `feature/user-scoped-storage-and-channels`. Nothing in this session was committed to git
(per this repo's standing rule: only commit when the user explicitly asks). Everything below is
**uncommitted working-tree state**.

## 1. What this conversation accomplished

Two distinct phases:

**A. Feature work** — built a WeChat native tap-menu and a "select-equipment" guided capture flow,
so users can tap buttons instead of typing every command, plus a multi-step category→equipment→
confirm→capture flow for deployments with a large browsable equipment list instead of a handful
of fixed channels.

**B. Live ops/debugging on `win11-bot-03`** ("bot-3", ansible inventory, `100.82.75.19`) — the
user reported the bot replying to text but not sending screenshots. Diagnosis (via ansible/WinRM,
read-only where possible) found and fixed three real, unrelated bugs. See §2 and §5.

## 2. What's in code (working tree, uncommitted)

### New files
- `src/screenshot_bot/workflow/menu.py` — builds the WeChat custom tap-menu
  (`build_menu_payload`), translates a tap's `EventKey` back to plain text (`event_key_to_text`).
  Two layouts depending on `equipment_catalog.enabled`: default (选择频道/帮助/水印帮助) vs.
  equipment-enabled (选择设备/选择频道/获取截图) — WeChat caps menus at 3 top-level buttons, so
  帮助/水印帮助 drop off the menu (not the bot) in the equipment layout.
- `src/screenshot_bot/wechat/menu_manager.py` — `WeChatMenuManager`, pushes/reads the menu via
  `cgi-bin/menu/create`/`menu/get` (added to `official_api.py`), mirrors `WeChatImageSender`'s
  retry-once-on-invalid-token pattern.
- `src/screenshot_bot/workflow/message_router.py` — **this is a rewrite/extension of an
  already-existing file**, not new logic from scratch; it now also handles the select-equipment
  flow's decisions (`equipment_start`, `equipment_category_selected`, `equipment_selected`,
  `equipment_confirmed`/`cancelled`, `equipment_capture*`), gated entirely behind a new
  `equipment_catalog_enabled` parameter so none of it activates for deployments that never
  configure `equipment_catalog`.
- `src/screenshot_bot/workflow/equipment_catalog.py` — reads the equipment CSV (`category,
  equipment, path` columns — same file `scripts/screenshot_equipment_list.py` already produces).
- `src/screenshot_bot/workflow/equipment_selection_tracker.py` — persists each sender's
  in-progress/confirmed equipment pick to `runtime/equipment-selection-tracker.json` (survives a
  restart, per explicit user decision — see §4).
- `src/screenshot_bot/workflow/equipment_prompts.py` — trigger words + reply-text builders for
  the equipment flow (mirrors `help_text.py`'s role for the channel flow).
- `src/screenshot_bot/browser/equipment_navigation.py` — the hash-route navigation + SVG-render-
  wait sequence (shared logic factored out so both the offline `screenshot_equipment_list.py` and
  the live webhook can navigate a tab to one equipment's graphic before screenshotting).
- `scripts/run_wechat_menu_sync.py` — CLI: `python run_wechat_menu_sync.py set|get`, pushes/reads
  the live menu. Wired into `scripts/Bot.ps1 menu set|get`.

### Modified files (this session)
- `src/screenshot_bot/workflow/wechat_image_reply.py` — wires menu-tap translation, equipment
  catalog/tracker, and refactors the capture path into a shared `_run_capture()` helper used by
  both normal channel capture and equipment capture.
- `src/screenshot_bot/workflow/help_text.py` — `_format_channel_list` renamed to public
  `format_channel_list` (now shared with `equipment_prompts.py`).
- `src/screenshot_bot/wechat/official_api.py` — added `create_menu`/`get_menu`.
- `src/screenshot_bot/browser/screenshot_service.py` — `capture()` gained
  `equipment_path`/`equipment_pane_height`/`equipment_settle_seconds` kwargs (optional, additive;
  plain channel capture unchanged).
- `config.example.json` — added `equipment_catalog` section (`enabled: false` by default).
- **`src/screenshot_bot/browser/cdp_multi_tab_service.py`** — **bug fix, not feature work**: added
  a per-tab `threading.Lock` (`_lock_for(name)`); all six CDP-issuing methods (`screenshot`,
  `login`, `keep_alive`, `navigate`, `refresh`, `navigate_equipment`) now acquire it before
  touching a tab. See §5 for why.
- **`src/screenshot_bot/wechat/webhook_server.py`** — **bug fix**: signature-verification
  failures (`do_GET`/`do_POST`) now get logged (console + JSONL for POST) before returning 403.
  Previously completely silent. See §5.
- **`scripts/Stop-WebhookBackground.ps1`** / **`scripts/Start-WebhookBackground.ps1`** /
  **`scripts/Bot.ps1`** — **bug fix**: added a port-ownership-based fallback kill/verify step,
  independent of the pre-existing `CommandLine`-regex matching. See §5.
- READMEs updated to match: root `README.md`, `src/screenshot_bot/workflow/README.md`,
  `src/screenshot_bot/browser/README.md`, `src/screenshot_bot/wechat/README.md`.

### Deployed to bot-3, not yet active
All of the above (`--tags app`, files only) has been `ansible-playbook deploy.yml --tags app
--limit win11-bot-03`'d successfully. **The currently-running webhook process on bot-3 is still
executing the pre-fix code** — none of the three bug fixes take effect until that process is
restarted. See §5/§6.

### Pre-existing uncommitted changes (not from this conversation — do not attribute or revert)
`git status` also shows `.gitignore`, `docs/DEBUG_HANDOFF.md`, `docs/PROJECT_SNAPSHOT.md`,
`docs/STABILIZATION_PLAN.md`, `src/screenshot_bot/browser/profile_manager.py`,
`src/screenshot_bot/screenshot_store/README.md`, `device-agent-mvp/`,
`scripts/crawl_graphics_tree.py` as modified/untracked. These were already in that state before
this conversation started (confirmed against the session's opening `git status` snapshot) or
appeared mid-session from outside this conversation (e.g. `profile_manager.py` gained a
`keep_alive` recovery closure that this session did not author — a system reminder flagged it as
an intentional external change to leave alone). Do not assume they're related to the work above.

## 3. What was only discussed, not implemented

- Nothing significant remains discussion-only from the feature work — the equipment flow went
  through an explicit clarifying-questions round (data source = CSV, capture target = navigate
  the user's joined channel tab, state = persisted, confirm = explicit) and all four answers are
  reflected in the shipped code.
- A `format_channel_list`-style helper consolidation was the only refactor considered and done;
  no other refactors were proposed and left undone.

## 4. Decisions later reversed or corrected

- **"Split-brain orphan process" diagnosis was wrong.** Early in the ops phase, two
  `python.exe` processes matching `run_wechat_official_webhook.py` (different interpreters) were
  diagnosed as a critical orphan-process bug and used to justify a `Bot.ps1 all restart`. Later
  in the same session this was **corrected**: it's normal — this venv's `Scripts\python.exe` is a
  launcher stub that spawns a child using a different (global) Python install; `Bot.ps1`'s own
  status-check comment already documents "expected 2 (1 parent + 1 child)". This was explicitly
  walked back to the user. The restart performed under that mistaken premise wasn't harmful, but
  the reasoning was wrong.
- **Explicit-confirm step for equipment selection**: the user picked "explicit confirm required"
  over "auto-confirm on pick" via the clarifying-questions round — this is a deliberate decision,
  not a reversal, but flagging it since auto-confirm (matching the channel-digit pattern) might
  seem like the more consistent default at a glance.
- **My own operational behavior was corrected mid-session**: I initially started/restarted the
  webhook on bot-3 myself (with confirmation) via ansible. The user then explicitly said "never
  start instance I do it mannually" — from that point on I stopped performing the start/restart
  step myself, restricting myself to read-only diagnosis, killing stuck processes, and syncing
  code fixes. **This is saved as a persistent memory** (see
  `feedback_never_start_webhook_remotely.md` in the auto-memory store) and must be honored by any
  future agent working on this repo, not just within this conversation.

## 5. Root causes found on bot-3 (all three fixed in code, deployed, **not yet live**)

1. **Wedged Chrome tab, permanent** — `keep_alive` (every `keep_alive_interval_seconds`, 60s) and
   `refresh` (every `refresh_interval_seconds`, 3600s) ran as independent background threads, each
   opening its own CDP WebSocket to the same tab, with nothing serializing them against each
   other or against `login()`/capture. Observed live: the tab wedged permanently (every
   subsequent `login()` retry timing out on "login page did not become ready") starting within
   ~10s of that tab's first scheduled hourly refresh, and never recovered on its own. Fixed with a
   per-tab lock in `CdpMultiTabService`; verified with a synthetic concurrency test (same-tab ops
   now serialize, different tabs still run fully parallel).
2. **Silent stop-verification blind spot** — `Stop-WebhookBackground.ps1`'s survivor check
   filters `Get-CimInstance Win32_Process` results by `CommandLine -match ...`; that field can
   come back `$null` for a process the querying session lacks privilege to introspect, and
   `$null -match` is `$false`, so the process silently never appears in the survivor list. Live
   evidence: the user's own `Bot.ps1 all restart` printed "Webhook stopped." twice with no error,
   yet the *exact same PIDs* from before the restart were still running afterward (confirmed via
   ansible/WinRM, which apparently has different visibility), and the new process crashed with
   `WinError 10048` (port already in use) against the still-alive old one. Fixed by adding a
   second, privilege-independent fallback: check who's actually listening on the configured port
   (`Get-NetTCPConnection`) and kill that PID directly if the CommandLine-based pass thinks
   nothing survived; throws a clear error if it still can't clear the port after 5 attempts,
   instead of silently declaring success.
3. **Silent signature-verification failures** — `do_GET`/`do_POST` returned 403 on a bad WeChat
   signature with zero trace in any log (console or JSONL). This produces an externally
   indistinguishable-from-healthy failure mode: process alive, tunnel connected, health check
   green, but literally nothing ever gets logged, because the request never reaches the
   message-processing code that writes to the JSONL. Fixed by logging both to console
   (`log_line("webhook", ...)`) and, for POST, to the JSONL event log. **Not confirmed** as the
   actual cause of the user's "no messages ever logged" symptom — just a real gap that's now
   closed so it's diagnosable if it recurs.

## 6. Risks / open items for the next agent

- **The bot-3 fixes are deployed but inert.** The webhook process running on bot-3 right now
  (as of last check) is still executing pre-fix code and was actively wedged (repeated "login
  page did not become ready" failures, ~70s cycle, no recovery). Do **not** restart it yourself —
  per the standing rule (§4), that is the user's action to take. If asked to verify the fixes,
  the verification only means anything *after* the user has restarted it.
- **Whether root cause #3 (signature logging) actually explains the reported symptom is
  unconfirmed.** After the user's next restart, if a test message still doesn't appear in the
  JSONL log, check for a new `"invalid signature"` line in `server.out.log` / the JSONL — that
  will settle it either way. If no such line appears either, the problem is likely upstream of
  this codebase entirely (WeChat console webhook URL misconfigured, wrong host, DNS/tunnel
  hostname routing) and needs investigation outside this repo (Cloudflare Zero Trust dashboard /
  WeChat MP admin console), which this agent has no access to.
- **The equipment-selection feature has only been exercised with mocks**, never against a real
  Chrome/WeChat account. `equipment_catalog.enabled` is `false` everywhere it's deployed
  (including bot-3's rendered config). If someone wants to test it live, they need: a real CSV at
  the configured `csv_path`, `equipment_catalog.enabled: true` in that host's config, a menu
  push (`Bot.ps1 menu set`), and a restart to pick up config changes — restart is, again, the
  user's action per §4.
- **`ansible/inventory.yml` contains plaintext WinRM credentials and a Cloudflare tunnel token**
  in cleartext. Not new to this session, but worth flagging: don't paste its contents into logs,
  commits, or anywhere outside this trusted context.
- **This session's own background-task plumbing was flaky**: a couple of long-running
  `ansible-playbook` calls via `wsl.exe -d AnsibleUbuntu` exceeded local timeouts and were
  reported as failed/backgrounded when the remote operation had actually completed successfully.
  If a future agent sees a WSL/ansible command "time out," re-check actual remote state via a
  fresh, narrowly-scoped read-only query before assuming the action failed — don't retry
  destructive/start actions reflexively on a timeout.
- **No git commit has been made.** All of §2's changes are sitting in the working tree. If the
  user wants this committed/pushed, that's a separate explicit ask (per repo convention, never
  done proactively).
- **Ansible diagnostic scratch files**: this session repeatedly created and deleted a temporary
  `ansible/_diag.yml` for read-only diagnostics. It should not exist in the working tree now
  (deleted after each use), but worth a quick `git status`/`ls ansible/` check if anything looks
  off.

## 7. Quick reference for whoever picks this up

- bot-3 = `win11-bot-03` in `ansible/inventory.yml`, `100.82.75.19`, install dir
  `C:\Tools\screenshot-bot-modular`.
- Ansible controller only runs from the `AnsibleUbuntu` WSL distro (WSL1 — the other WSL2 distros
  on this machine fail with a nested-virtualization error in this sandboxed environment):
  `wsl.exe -d AnsibleUbuntu -- bash -lc "cd /mnt/c/Users/frank/screenshot-bot-modular/ansible && ansible-playbook -i inventory.yml <playbook> --limit win11-bot-03 ..."`
- Safe code sync: `ansible-playbook deploy.yml --tags app --limit win11-bot-03` (files only,
  re-renders that host's `config.json` from template — does not touch secrets or restart
  anything).
- **Never** run `bot_command=webhook bot_action=start|restart` or `bot_command=all
  bot_action=restart` (or the equivalent `webhook-start.yml`/`webhook-restart.yml`) against any
  of `win11-bot-01/02/03` without the user explicitly asking for *that specific action* in the
  current conversation — see the persisted memory note.
