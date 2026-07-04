# Ansible Deployment

Deploys the modular WeChat Official Account webhook to Windows 11 hosts over WinRM.
Infra (inventory hosts/credentials, WeChat Official Account secrets) is intentionally reused
from the `screenshot-bot` project's Ansible setup, since both projects target the same
Windows lab machines and the same WeChat Official Account.

This repo excludes wx-cli, desktop WeChat polling, UI-driven WeChat sending, and Cloudflare
tunnel management. Deploy stages only cover: directories, application files, Python venv,
`ScreenshotTool.exe` build, and secrets delivery. Browser targets are named tabs inside one
shared Chrome process (`browser_targets.debug_port`/`profile_dir`), launched and owned by
this app itself; nothing here manages Chrome lifecycle at deploy time.

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
This repo does not start or manage a tunnel; point an existing tunnel or reverse proxy at
`http://127.0.0.1:<port><path>` on the target host.

```bash
ansible-playbook -i ansible/inventory.yml ansible/secrets-status.yml
ansible-playbook -i ansible/inventory.yml ansible/webhook-start.yml
ansible-playbook -i ansible/inventory.yml ansible/webhook-status.yml
ansible-playbook -i ansible/inventory.yml ansible/webhook-logs.yml
ansible-playbook -i ansible/inventory.yml ansible/webhook-stop.yml
```

## Notes

- `inventory.yml`, `group_vars/screenshot_bot_modular.yml`, and `files/secrets.local.ps1`
  should remain uncommitted (see `.gitignore`).
- The scheduled task option starts the webhook once immediately (`ansible/webhook-start.yml`);
  set `create_startup_task: true` in group vars to also start it at logon.
