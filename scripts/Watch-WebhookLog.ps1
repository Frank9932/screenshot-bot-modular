<#
.SYNOPSIS
Live-tails the webhook's JSONL event log, printing one readable, colorized line per message
instead of raw JSON -- a professional `tail -f | jq` style watcher for this project's log shape.

.DESCRIPTION
Reads logs/wechat-official-webhook-events.jsonl (path resolved from config.json, same as every
other script here) and follows it as it grows. Each line is parsed defensively: a line still
mid-write (a partial/invalid JSON fragment, which can happen since the writer appends line by
line while this reads concurrently) is skipped with a one-line warning instead of crashing the
whole watcher.

Prints one summary line per event: timestamp, sender, message type, channel, what was triggered,
and outcome. Failures (ok:false, a non-zero WeChat send errcode, or a capture_error) print in red
with the actual error text; successes print in green. Per-call timing (capture_ms/total_latency,
and token_ms/upload_ms/send_ms when present) is included so a slow reply is visible immediately
instead of requiring a follow-up log dig -- see root README.md -> "Logs" for what those fields
mean.

.EXAMPLE
scripts\Watch-WebhookLog.ps1
scripts\Watch-WebhookLog.ps1 -OnlyErrors
scripts\Watch-WebhookLog.ps1 -TouserFilter oLKTb3IShJ05mHHfj8n8bns7R6XM
scripts\Watch-WebhookLog.ps1 -ConfigPath .\config.example.json -Tail 50
#>
param(
    [string]$ConfigPath = (Join-Path $PSScriptRoot "..\config.json"),
    [string]$LogPath = "",
    [int]$Tail = 20,
    # Only print events that failed (ok:false, non-zero send errcode, or a capture_error) --
    # useful for watching a busy production log without success events scrolling errors away.
    [switch]$OnlyErrors,
    # Only print events from this one WeChat user (FromUserName/touser) -- useful when
    # reproducing/debugging one sender's session without everyone else's traffic interleaved.
    [string]$TouserFilter = ""
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

# Log content is Chinese-heavy (channel prompts, watermark commands). The console host's default
# output encoding on a non-UTF8-codepage Windows install can't represent those characters and
# silently substitutes "?" -- forcing UTF-8 here fixes display regardless of the system codepage.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Get-JsonValue {
    param([object]$Object, [string]$Name, [object]$Default = "")
    if ($null -ne $Object -and $Object.PSObject.Properties.Name -contains $Name -and $null -ne $Object.$Name) { return $Object.$Name }
    return $Default
}

function Resolve-EventsLogPath {
    if (![string]::IsNullOrWhiteSpace($LogPath)) { return $LogPath }
    try {
        $config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $webhook = Get-JsonValue $config "wechat_official_webhook" $null
        $configured = Get-JsonValue $webhook "log_path" ""
        if (![string]::IsNullOrWhiteSpace($configured)) {
            $root = Split-Path -Parent (Resolve-Path -LiteralPath $ConfigPath)
            return (Join-Path $root $configured)
        }
    } catch {
    }
    return (Join-Path $PSScriptRoot "..\logs\wechat-official-webhook-events.jsonl")
}

function Format-ContentPreview {
    param([string]$Text, [int]$MaxLength = 40)
    if ([string]::IsNullOrEmpty($Text)) { return "" }
    $oneLine = $Text -replace "\r?\n", " \ "
    if ($oneLine.Length -gt $MaxLength) { return $oneLine.Substring(0, $MaxLength) + "..." }
    return $oneLine
}

function Format-EventLine {
    param([object]$Event)

    $touser = Get-JsonValue $Event "touser" ""
    $msgType = Get-JsonValue $Event "msg_type" ""
    $content = Format-ContentPreview (Get-JsonValue $Event "content" "")
    $channel = Get-JsonValue $Event "browser_team_id" ""
    $triggerKind = Get-JsonValue $Event "trigger_kind" ""
    $ok = Get-JsonValue $Event "ok" $false
    $ignored = Get-JsonValue $Event "ignored" $false
    $sendResponse = Get-JsonValue $Event "send_response" $null
    $sendErrcode = Get-JsonValue $sendResponse "errcode" 0
    $sendErrmsg = Get-JsonValue $sendResponse "errmsg" ""
    $captureError = Get-JsonValue $Event "capture_error" ""
    $captureMs = Get-JsonValue $Event "capture_ms" $null
    $totalLatency = Get-JsonValue $Event "total_latency" $null
    $tokenMs = Get-JsonValue $Event "token_ms" $null
    $uploadMs = Get-JsonValue $Event "upload_ms" $null
    $sendMs = Get-JsonValue $Event "send_ms" $null
    $receivedAt = Get-JsonValue $Event "received_at" ""
    $timeLabel = try { ([DateTimeOffset]::Parse($receivedAt)).ToLocalTime().ToString("HH:mm:ss") } catch { "??:??:??" }

    $isFailure = (-not $ok) -or ($sendErrcode -ne 0) -or (![string]::IsNullOrEmpty($captureError))
    $color = if ($isFailure) { "Red" } elseif ($ignored) { "DarkGray" } else { "Green" }

    $parts = New-Object System.Collections.Generic.List[string]
    $parts.Add("[$timeLabel]")
    $parts.Add("user=$touser")
    $parts.Add("type=$msgType")
    if ($content) { $parts.Add("content=`"$content`"") }
    if ($channel) { $parts.Add("channel=$channel") }
    if ($triggerKind) { $parts.Add("kind=$triggerKind") }
    if ($null -ne $captureMs) { $parts.Add(("capture={0}ms" -f [math]::Round([double]$captureMs))) }
    if ($null -ne $tokenMs -and [double]$tokenMs -gt 5) { $parts.Add(("token={0}ms" -f [math]::Round([double]$tokenMs))) }
    if ($null -ne $uploadMs) { $parts.Add(("upload={0}ms" -f [math]::Round([double]$uploadMs))) }
    if ($null -ne $sendMs) { $parts.Add(("send={0}ms" -f [math]::Round([double]$sendMs))) }
    if ($null -ne $totalLatency) { $parts.Add(("total={0}ms" -f [math]::Round([double]$totalLatency))) }

    if ($ignored) {
        $parts.Add("IGNORED (" + (Get-JsonValue $Event "reason" "") + ")")
    } elseif ($isFailure) {
        $parts.Add("FAIL")
        if ($sendErrcode -ne 0) { $parts.Add("send_errcode=$sendErrcode send_errmsg=`"$sendErrmsg`"") }
        if (![string]::IsNullOrEmpty($captureError)) { $parts.Add("capture_error=`"$captureError`"") }
    } else {
        $parts.Add("OK")
    }

    Write-Host ($parts -join "  ") -ForegroundColor $color
}

$resolvedLogPath = Resolve-EventsLogPath
if (!(Test-Path -LiteralPath $resolvedLogPath)) {
    Write-Warning "Log file does not exist yet, waiting for it to be created: $resolvedLogPath"
    $waitDeadline = (Get-Date).AddSeconds(30)
    while (!(Test-Path -LiteralPath $resolvedLogPath) -and (Get-Date) -lt $waitDeadline) { Start-Sleep -Milliseconds 500 }
    if (!(Test-Path -LiteralPath $resolvedLogPath)) { throw "Log file never appeared: $resolvedLogPath" }
}

Write-Host "Watching $resolvedLogPath (Ctrl+C to stop)" -ForegroundColor Cyan
if ($OnlyErrors) { Write-Host "Filter: errors only" -ForegroundColor Cyan }
if ($TouserFilter) { Write-Host "Filter: touser = $TouserFilter" -ForegroundColor Cyan }
Write-Host ""

Get-Content -LiteralPath $resolvedLogPath -Wait -Tail $Tail -Encoding UTF8 | ForEach-Object {
    $line = $_
    if ([string]::IsNullOrWhiteSpace($line)) { return }

    $event = $null
    try {
        $event = $line | ConvertFrom-Json
    } catch {
        Write-Warning "Skipping unparseable log line: $($_.Exception.Message)"
        return
    }

    if ($TouserFilter -and (Get-JsonValue $event "touser" "") -ne $TouserFilter) { return }

    if ($OnlyErrors) {
        $ok = Get-JsonValue $event "ok" $false
        $sendResponse = Get-JsonValue $event "send_response" $null
        $sendErrcode = Get-JsonValue $sendResponse "errcode" 0
        $captureError = Get-JsonValue $event "capture_error" ""
        $isFailure = (-not $ok) -or ($sendErrcode -ne 0) -or (![string]::IsNullOrEmpty($captureError))
        if (-not $isFailure) { return }
    }

    Format-EventLine $event
}
