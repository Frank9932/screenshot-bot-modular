# Copy this file to secrets.local.ps1 (same directory) and fill in real values.
# ansible/files/secrets.local.ps1 is ignored by Git; the deploy playbook copies it
# to <bot_install_dir>\secrets.local.ps1 on the target machine.

$env:WECHAT_APPID = "paste-appid-here"
$env:WECHAT_APPSECRET = "paste-appsecret-here"
$env:WECHAT_OFFICIAL_WEBHOOK_TOKEN = "paste-webhook-token-here"
