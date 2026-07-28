param(
    [string]$PlatformBin = "C:\Program Files\1cv8\8.5.1.1150\bin",
    [string]$VirtualDir = "fresh-unf",
    [string]$PublishDir = "C:\inetpub\wwwroot\fresh-unf",
    [string]$ConnectionString = 'Srvr="192.168.2.126:2541";Ref="fresh-unf";',
    [switch]$DeleteOnly
)

$ErrorActionPreference = "Stop"

$webinst = Join-Path $PlatformBin "webinst.exe"
if (-not (Test-Path $webinst)) {
    throw "webinst.exe not found: $webinst"
}

if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    throw "Этот скрипт нужно запускать из PowerShell с правами администратора."
}

if ($DeleteOnly) {
    & $webinst -delete -iis -wsdir $VirtualDir -dir $PublishDir
    exit $LASTEXITCODE
}

New-Item -ItemType Directory -Force -Path $PublishDir | Out-Null

& $webinst `
    -publish `
    -iis `
    -wsdir $VirtualDir `
    -dir $PublishDir `
    -connstr $ConnectionString

exit $LASTEXITCODE
