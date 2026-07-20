param(
    [string]$StatePath = (Join-Path $PSScriptRoot "..\runtime\wechat-official-webhook-state.json"),
    # Optional: if given, verified as a second, independent signal after the CommandLine-based
    # kill loop below (see the port-based fallback near the end of this script for why).
    [int]$Port = 0
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

if (Test-Path -LiteralPath $StatePath) {
    $state = Get-Content -LiteralPath $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($null -ne $state.webhook_pid -and [int]$state.webhook_pid -gt 0) {
        Stop-Process -Id ([int]$state.webhook_pid) -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $StatePath -Force -ErrorAction SilentlyContinue
}

# Belt and suspenders beyond the tracked PID above: Windows lets a second process bind the same
# port via SO_REUSEADDR, so a crash, a manual kill of just the tracked PID, or any prior restart
# that didn't go through this script can all leave an untracked orphan still running and still
# serving requests. Stop every process actually running this webhook's entry script, not just
# the one this state file happened to remember.
#
# This is a retry-and-verify loop, not a single blind pass: Get-CimInstance/WMI can occasionally
# miss a process on the first query (observed in production under host memory pressure), which
# would silently leave an orphan whose background keep_alive/refresh threads keep running against
# a Chrome tab that's since been closed/replaced -- producing exactly the confusing
# "tab not debuggable" / "connection actively refused" log noise from a process that was supposed
# to already be dead.
for ($attempt = 1; $attempt -le 5; $attempt++) {
    $survivors = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -match [regex]::Escape("run_wechat_official_webhook.py") })
    if ($survivors.Count -eq 0) { break }
    foreach ($proc in $survivors) {
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 500
}

$remaining = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match [regex]::Escape("run_wechat_official_webhook.py") })
if ($remaining.Count -gt 0) {
    # A blind Write-Warning here previously let Start-WebhookBackground.ps1 proceed to launch a
    # second instance alongside the un-killed one -- e.g. when this script runs from a
    # non-elevated console but the survivor was started with higher integrity (schtasks /RL
    # HIGHEST): Stop-Process fails with access-denied, which -ErrorAction SilentlyContinue
    # swallows, so the failure was invisible until two instances were already racing over the
    # same shared Chrome/tab state. Throw instead so the caller sees this before starting anew.
    throw "Could not stop $($remaining.Count) webhook process(es) after 5 attempts: $($remaining.ProcessId -join ', '). If this was run from a non-elevated console while the running instance has higher privileges, re-run elevated."
}

# Port-based fallback, independent of the CommandLine-matching loop above: Get-CimInstance's
# CommandLine property can silently come back $null for a process this session doesn't have
# sufficient privilege to introspect (observed live: a python.exe child spawned via this venv's
# own launcher-stub mechanism, running under a different Python install than the venv's own
# Scripts\python.exe, was invisible to CommandLine matching from one session while fully visible
# from another more-privileged one). `$null -match <pattern>` is false, so that process silently
# never entered $survivors/$remaining above at all -- this loop declared success while the
# process was still alive, still holding the port, and the very next start attempt then crashed
# with "WinError 10048: address already in use" against it. Checking who is ACTUALLY listening on
# the configured port sidesteps that blind spot entirely: Get-NetTCPConnection's OwningProcess
# doesn't depend on being able to read that process's command line, only that it's listening.
if ($Port -gt 0) {
    for ($attempt = 1; $attempt -le 5; $attempt++) {
        $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -eq $listener) { break }
        Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
    }
    $stillListening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $stillListening) {
        throw "Port $Port is still held by pid $($stillListening.OwningProcess) after 5 attempts -- could not stop it (possibly a privilege/visibility issue; try re-running elevated). Webhook was not fully stopped."
    }
}

Write-Host "Webhook stopped."
