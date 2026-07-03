param(
    [string]$SourcePath = (Join-Path $PSScriptRoot "ScreenshotTool.cs"),
    [string]$OutputPath = (Join-Path $PSScriptRoot "ScreenshotTool.exe")
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$frameworkRoot = Join-Path $env:WINDIR "Microsoft.NET\Framework64"
$compiler = Get-ChildItem -LiteralPath $frameworkRoot -Filter csc.exe -Recurse |
    Sort-Object FullName -Descending |
    Select-Object -First 1

if ($null -eq $compiler) {
    throw "csc.exe not found under $frameworkRoot"
}

& $compiler.FullName /nologo /target:exe /out:$OutputPath /r:System.dll /r:System.Drawing.dll /r:System.Windows.Forms.dll /r:System.Web.Extensions.dll $SourcePath
if ($LASTEXITCODE -ne 0) {
    throw "C# compiler failed."
}

Write-Host "Built: $OutputPath"
