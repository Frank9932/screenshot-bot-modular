# Ansible Deployment

Deploys the modular WeChat Official Account webhook to Windows 11 hosts over WinRM.
Infra (inventory hosts/credentials, WeChat Official Account secrets) is intentionally reused
from the `screenshot-bot` project's Ansible setup, since both projects target the same
Windows lab machines and the same WeChat Official Account.

This repo excludes wx-cli, desktop WeChat polling, UI-driven WeChat sending, and Cloudflare
tunnel management. Deploy stages only cover: directories, application files, Python venv,
`ScreenshotTool.exe` build, and secrets delivery. Browser targets share the same Chrome
DevTools ports as `screenshot-bot`'s `browser_targets`, so an already-running Chrome profile
from that project is reused as-is; nothing here manages Chrome lifecycle at deploy time.

## Prepare Inventory

```bash
cp inventory.example.yml inventory.yml
cp group_vars/screenshot_bot_modular.example.yml group_vars/screenshot_bot_modular.yml
cp files/secrets.local.example.ps1 files/secrets.local.ps1
```

Edit `inventory.yml` with real WinRM credentials, `group_vars/screenshot_bot_modular.yml`
with real deployment values, and `files/secrets.local.ps1` with the real
`WECHAT_APPID` / `WECHAT_APPSECRET` / `WECHAT_OFFICIAL_WEBHOOK_TOKEN` values. None of these
three files are committed to Git.

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
