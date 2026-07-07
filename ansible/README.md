# Ansible Deployment

Deploys the modular WeChat Official Account webhook to Windows 11 hosts over WinRM.
Infra (inventory hosts/credentials, WeChat Official Account secrets) is intentionally reused
from the `screenshot-bot` project's Ansible setup, since both projects target the same
Windows lab machines and the same WeChat Official Account.

This repo excludes wx-cli, desktop WeChat polling, and UI-driven WeChat sending. Deploy stages
only cover: directories, application files, Python venv, `ScreenshotTool.exe` build, and secrets
delivery. Browser targets are named tabs inside one shared Chrome process
(`browser_targets.debug_port`/`profile_dir`), launched and owned by this app itself; nothing
here manages Chrome lifecycle at deploy time.

The deploy stage still doesn't manage a *production* tunnel (bring your own stable ingress for
real use), but `ansible/tunnel-start.yml`/`tunnel-stop.yml`/`tunnel-status.yml` are provided as
optional convenience tooling for a throwaway Cloudflare quick tunnel — useful for testing
against a real WeChat account without a permanent public endpoint. See "Runtime Operations"
below.

## Prepare Inventory

```bash
cp inventory.example.yml inventory.yml
cp group_vars/screenshot_bot_modular.example.yml group_vars/screenshot_bot_modular.yml
cp files/secrets.local.example.ps1 files/secrets.local.ps1
```

Edit `inventory.yml` with real WinRM credentials, `group_vars/screenshot_bot_modular.yml`
with real deployment values, and `files/secrets.local.ps1` with the real
`WECHAT_APPID` / `WECHAT_APPSECRET` / `WECHAT_OFFICIAL_WEBHOOK_TOKEN` values (required). None of
these three files are committed to Git.

If `group_vars/screenshot_bot_modular.yml` enables a `browser_targets` target with a `login`
block (e.g. the `webstation-test` target used for testing against a login-gated internal site),
`files/secrets.local.ps1` must also set that target's `username_env`/`password_env` pair —
by default `WEBSTATION_USERNAME` / `WEBSTATION_PASSWORD`. These are optional: only required for
targets that set `login.enabled: true`; omit them if no configured target needs a login.
`ansible/secrets-status.yml` reports whether they're set (see "Runtime Operations" below), but
unlike the WeChat secrets it does not fail deployment if they're missing, since login-gated
targets are opt-in per environment.

The example config maps WeChat team numbers `1`-`5` to the 5 tabs of one `webstation-test`
target (identical `name`/`start_url`/`app_url`/`tab_count`/`login` on all 5 entries, only
`"tab"` differs 0-4) — one login/credential pair covers all 5, since every tab shares that one
Chrome process's session cookie. See `src/screenshot_bot/browser/README.md` → "Team-per-tab
targets" for the full pattern.

## Run

Use a Linux Ansible controller for Windows WinRM deployment (see `screenshot-bot/ansible/README.md`
for the `AnsibleUbuntu` WSL notes this project follows too):

```bash
ansible-playbook -i ansible/inventory.yml ansible/deploy.yml
```

Run a single stage when iterating:

```bash
ansible-playbook -i ansible/inventory.yml ansible/deploy.yml --tags app
ansible-playbook -i ansible/inventory.yml ansible/deploy.yml --tags python
ansible-playbook -i ansible/inventory.yml ansible/deploy.yml --tags secrets
```

## Runtime Operations

The webhook server runs locally on `bot_config.wechat_official_webhook.port`
(default `8791`, distinct from `screenshot-bot`'s `8790` so both can run on the same host).
For production, point an existing tunnel or reverse proxy at `http://127.0.0.1:<port><path>`
on the target host; for testing, the optional quick-tunnel scripts below can stand one up.

Always pass `--limit <host>` if your inventory has more than one host in the group, so these
don't touch a different machine's deployment.

### Unified CLI (`scripts/Bot.ps1`)

The single entry point for day-to-day commands, usable both directly on the machine (RDP'd in)
and remotely through the `ansible/bot.yml` wrapper:

```powershell
# on the machine directly
scripts\Bot.ps1 status              # webhook + tunnel + Chrome process count, one view
scripts\Bot.ps1 webhook restart      # clean stop + start + print browser warm_up
scripts\Bot.ps1 browser restart      # kill Chrome too, then restart the webhook (fresh Chrome + re-login)
scripts\Bot.ps1 browser warmup       # retry login for every target WITHOUT restarting anything
scripts\Bot.ps1 tunnel start
```

```bash
# remotely, via ansible
ansible-playbook -i ansible/inventory.yml ansible/bot.yml --limit <host> -e "bot_command=status"
ansible-playbook -i ansible/inventory.yml ansible/bot.yml --limit <host> -e "bot_command=browser bot_action=restart"
```

`webhook restart` (Python process only) intentionally does **not** kill Chrome — a process
restart adopts whatever Chrome is already running, by design, so a crash/redeploy doesn't lose
an authenticated session. If Chrome itself is the thing that's stuck (not just the webhook
process), use `browser restart` instead, which kills Chrome first. `browser warmup` is the
non-disruptive option: it retries login for every target in a one-off process that safely
shares the already-running Chrome (via `adopt_tab`), without touching the live webhook process
at all — useful right after fixing a credential.

The commands below are the individual playbooks `Bot.ps1`/`bot.yml` wrap; use them directly if
you want one specific step rather than the combined command:

```bash
ansible-playbook -i ansible/inventory.yml ansible/secrets-status.yml
ansible-playbook -i ansible/inventory.yml ansible/webhook-start.yml
ansible-playbook -i ansible/inventory.yml ansible/webhook-restart.yml   # clean stop + start + print browser warm_up
ansible-playbook -i ansible/inventory.yml ansible/webhook-status.yml
ansible-playbook -i ansible/inventory.yml ansible/webhook-logs.yml
ansible-playbook -i ansible/inventory.yml ansible/webhook-stop.yml
```

`webhook-stop.yml`/`Stop-WebhookBackground.ps1` and `Start-WebhookBackground.ps1` (which calls
it before launching) both stop *every* process actually running `run_wechat_official_webhook.py`,
not just the one PID the state file remembers — Windows lets a second process bind the same
port via `SO_REUSEADDR`, so a narrower stop can leave an orphan silently still serving requests.
`webhook-restart.yml` combines a clean stop + start + waits for and prints the browser
`warm_up()` result, so you can see target/tab login state right after a restart instead of
digging through logs separately.

### Optional quick tunnel

For testing against a real WeChat account without standing up permanent ingress:

```bash
ansible-playbook -i ansible/inventory.yml ansible/tunnel-start.yml --limit <host>
ansible-playbook -i ansible/inventory.yml ansible/tunnel-status.yml --limit <host>
ansible-playbook -i ansible/inventory.yml ansible/tunnel-stop.yml --limit <host>
```

`tunnel-start.yml` prints the resulting `https://<random>.trycloudflare.com/wechat/official/webhook`
URL — paste that into the WeChat MP console (Settings & Development → Basic Configuration →
Server Configuration). Re-running `tunnel-start.yml` stops the previously tracked tunnel first
and starts a fresh one (new URL each time — quick tunnels are ephemeral and have no uptime
guarantee; re-paste the URL after every restart). It never touches an *untracked* `cloudflared`
process, so an unrelated tunnel already running on the same host (e.g. a different project's) is
left alone.

If the host already has a named Cloudflare tunnel configured (a `config.yml` under the default
`~/.cloudflared` directory, e.g. for a different project sharing the host), `Start-PublicTunnel.ps1`
isolates itself from it by overriding `USERPROFILE` for just that process — otherwise cloudflared
picks up that config's credentials and evaluates every request against *that* tunnel's ingress
rules, which don't know about our new quick-tunnel hostname and 404 everything.

## Notes

- `inventory.yml`, `group_vars/screenshot_bot_modular.yml`, and `files/secrets.local.ps1`
  should remain uncommitted (see `.gitignore`).
- The scheduled task option starts the webhook once immediately (`ansible/webhook-start.yml`);
  set `create_startup_task: true` in group vars to also start it at logon.
