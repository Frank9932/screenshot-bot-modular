param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot "..\config.json"),
    [int]$Port = 0,
    [string]$CloudflaredPath = ""
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")

function Get-JsonValue {
    param([object]$Object, [string]$Name, [object]$Default = "")
    if ($null -ne $Object -and $Object.PSObject.Properties.Name -contains $Name -and $null -ne $Object.$Name) { return $Object.$Name }
    return $Default
}

function Resolve-Cloudflared {
    param([string]$Explicit)
    if (![string]::IsNullOrWhiteSpace($Explicit) -and (Test-Path -LiteralPath $Explicit)) { return $Explicit }
    $candidates = @(
        "C:\Program Files (x86)\cloudflared\cloudflared.exe",
        "C:\Program Files\cloudflared\cloudflared.exe",
        (Join-Path $root "runtime\cloudflared\cloudflared.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    $command = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($null -ne $command) { return $command.Source }
    throw "cloudflared.exe not found. Install it (winget install Cloudflare.cloudflared) or pass -CloudflaredPath."
}

if ($Port -le 0) {
    $config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $webhook = Get-JsonValue $config "wechat_official_webhook" $null
    $Port = [int](Get-JsonValue $webhook "port" 8791)
}

$cloudflared = Resolve-Cloudflared -Explicit $CloudflaredPath
$runtimeDir = Join-Path $root "runtime"
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null

$statePath = Join-Path $runtimeDir "public-tunnel-state.json"
$outLog = Join-Path $runtimeDir "public-tunnel.out.log"
$errLog = Join-Path $runtimeDir "public-tunnel.err.log"

# Stop any tunnel this script previously started (tracked by PID in the state file) before
# starting a new one -- never touch untracked cloudflared processes, since this host may also
# be running an unrelated tunnel (e.g. a different project's) that must not be disturbed.
if (Test-Path -LiteralPath $statePath) {
    try {
        $previous = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($null -ne $previous.pid) {
            Stop-Process -Id ([int]$previous.pid) -Force -ErrorAction SilentlyContinue
        }
    } catch {
    }
}
Remove-Item -LiteralPath $statePath, $outLog, $errLog -Force -ErrorAction SilentlyContinue

# Isolate this quick tunnel from any pre-existing named-tunnel config in the default
# ~/.cloudflared directory. If cloudflared finds a config.yml there (e.g. a different, unrelated
# named tunnel already configured on this host for another project), it evaluates every request
# against THAT tunnel's ingress rules instead of genuinely anonymous quick-tunnel routing --
# every request 404s at Cloudflare's edge because none of that config's ingress hostnames match
# our new quick-tunnel hostname. Pointing USERPROFILE at a directory with no .cloudflared folder
# avoids this without touching the existing config at all.
$isolatedHome = Join-Path $runtimeDir "cloudflared-isolated-home"
New-Item -ItemType Directory -Path $isolatedHome -Force | Out-Null

$previousUserProfile = $env:USERPROFILE
$env:USERPROFILE = $isolatedHome
try {
    $process = Start-Process -FilePath $cloudflared -ArgumentList "tunnel", "--url", "http://127.0.0.1:$Port", "--no-autoupdate" -WindowStyle Hidden -PassThru -RedirectStandardOutput $outLog -RedirectStandardError $errLog
} finally {
    $env:USERPROFILE = $previousUserProfile
}

$deadline = (Get-Date).AddSeconds(20)
$tunnelUrl = ""
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 500
    if ($process.HasExited) { throw "cloudflared exited before producing a tunnel URL. See $errLog" }
    $combined = (Get-Content -LiteralPath $outLog -Raw -ErrorAction SilentlyContinue) + (Get-Content -LiteralPath $errLog -Raw -ErrorAction SilentlyContinue)
    $match = [regex]::Match($combined, "https://[a-zA-Z0-9-]+\.trycloudflare\.com")
    if ($match.Success) { $tunnelUrl = $match.Value; break }
}
if ($tunnelUrl -eq "") {
    throw "Timed out waiting for a Cloudflare tunnel URL. See $errLog"
}

$webhookPath = ""
try {
    $config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $webhook = Get-JsonValue $config "wechat_official_webhook" $null
    $webhookPath = [string](Get-JsonValue $webhook "path" "/wechat/official/webhook")
} catch {
}

$state = [pscustomobject]@{
    started_at = (Get-Date).ToString("o")
    port = $Port
    pid = $process.Id
    tunnel_url = $tunnelUrl
    webhook_url = "$tunnelUrl$webhookPath"
    out_log = $outLog
    err_log = $errLog
}
$state | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $statePath -Encoding UTF8

Write-Host "Tunnel is up."
Write-Host "Paste this into the WeChat MP console (Settings & Development -> Basic Configuration -> Server Configuration):"
Write-Host $state.webhook_url
$state | ConvertTo-Json -Depth 5
