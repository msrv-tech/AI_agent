<#
.SYNOPSIS
    Сборка расширения из XML (при необходимости), загрузка в конфигурацию, обновление БД и запуск 1С.

.DESCRIPTION
    Всё в одном скрипте:
    0) При -BuildFromXml: сборка .cfe из каталога xml (LoadConfigFromFiles → DumpCfg).
    1) Загрузка расширения из .cfe в конфигурацию БД (/LoadCfg).
    2) Обновление конфигурации БД (/UpdateDBCfg).
    3) Запуск 1С в режиме предприятия (по умолчанию скрипт не ждёт закрытия клиента; для ожидания укажите -Wait).

.EXAMPLE
    .\update-extension-and-run-db.ps1 -BuildFromXml
    Полный цикл: сборка из xml → загрузка .cfe → обновление БД → запуск 1С.

.EXAMPLE
    .\update-extension-and-run-db.ps1
    Без сборки: только загрузка существующего .cfe, обновление БД, запуск 1С.

.EXAMPLE
    .\update-extension-and-run-db.ps1 -SkipLoadExtension
    Только обновление БД и запуск (расширение уже загружено).

.EXAMPLE
    .\update-extension-and-run-db.ps1 -BuildFromXml -Wait
    Полный цикл; скрипт ждёт закрытия 1С (по умолчанию не ждёт).
#>

[CmdletBinding()]
param(
    [string]$PlatformExe = 'C:\Program Files\1cv8\8.5.1.1150\bin\1cv8.exe',
    [string]$ConnectionString = '',
    [string]$UserName = '',
    [string]$Password = '',
    [string]$LogDir = "$PSScriptRoot\logs",
    [string]$XmlPath = (Join-Path (Split-Path $PSScriptRoot -Parent) 'xml'),
    [string]$ExtensionCfePath = (Join-Path (Split-Path $PSScriptRoot -Parent) 'bin\ИИ_Агент.cfe'),
    [string]$ExtensionName = 'ИИ_Агент',
    [switch]$BuildFromXml,
    [switch]$SkipLoadExtension,
    [switch]$SkipDbUpdate,
    [switch]$SkipRunClient,
    [switch]$Wait
)

$ErrorActionPreference = 'Stop'

# Загрузка .env из корня проекта (если есть)
$projectRoot = Split-Path $PSScriptRoot -Parent
$envPath = Join-Path $projectRoot '.env'
if (Test-Path -LiteralPath $envPath -PathType Leaf) {
    Get-Content -LiteralPath $envPath -Encoding UTF8 | ForEach-Object {
        if ($_ -match '^\s*#' -or $_ -notmatch '^\s*([A-Za-z0-9_]+)\s*=\s*(.*)$') { return }
        if ($_ -match '^\s*([A-Za-z0-9_]+)\s*=\s*(.*)$') {
            [System.Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), 'Process')
        }
    }
}

# Строка подключения: параметр → 1C_CONNECTION_STRING из .env/env → значение по умолчанию
if (-not $ConnectionString -and $env:1C_CONNECTION_STRING) { $ConnectionString = $env:1C_CONNECTION_STRING }
if (-not $ConnectionString) { $ConnectionString = 'File="D:\EDT_base\КонфигурацияТест";' }
$env:1C_CONNECTION_STRING = $ConnectionString

# Кодировка консоли UTF-8 для корректного отображения кириллицы
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
try { chcp 65001 | Out-Null } catch { }
try { $Host.UI.RawUI.OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

function Test-RequiredFile {
    param(
        [Parameter(Mandatory)]
        [string]$Path,
        [Parameter(Mandatory)]
        [string]$Description
    )
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Файл $Description не найден: $Path"
    }
}

function Test-RequiredPath {
    param(
        [Parameter(Mandatory)]
        [string]$Path,
        [Parameter(Mandatory)]
        [string]$Description,
        [bool]$Directory = $false
    )
    $exists = if ($Directory) { Test-Path -LiteralPath $Path -PathType Container } else { Test-Path -LiteralPath $Path -PathType Leaf }
    if (-not $exists) { throw "$Description не найден: $Path" }
}

function Invoke-Platform {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments,
        [Parameter(Mandatory)]
        [string]$OperationName,
        [switch]$NoWait
    )
    Write-Host "==> $OperationName"
    Write-Host ("    1cv8.exe {0}" -f ($Arguments -join ' '))
    $process = Start-Process -FilePath $PlatformExe -ArgumentList $Arguments -PassThru
    if (-not $NoWait) {
        $process | Wait-Process
        if ($process.ExitCode -ne 0) {
            throw "Команда 1cv8 для операции '$OperationName' завершилась с кодом $($process.ExitCode)"
        }
    }
}

# Проверки
Test-RequiredFile -Path $PlatformExe -Description 'платформы 1cv8'
if ($BuildFromXml) {
    Test-RequiredPath -Path $XmlPath -Description 'Каталог выгрузки (xml)' -Directory $true
}
if (-not (Test-Path -LiteralPath $LogDir)) {
    Write-Host "Создаю каталог логов: $LogDir"
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

$updateLog = Join-Path -Path $LogDir -ChildPath 'update-db.log'
$buildLoadLog = Join-Path -Path $LogDir -ChildPath 'build-load.log'
$buildDumpLog = Join-Path -Path $LogDir -ChildPath 'build-dump.log'
$cfeFullPath = $null
if (-not $SkipLoadExtension) {
    $cfeFullPath = [System.IO.Path]::GetFullPath($ExtensionCfePath)
    if (-not $BuildFromXml) {
        Test-RequiredFile -Path $cfeFullPath -Description 'расширения (.cfe)'
    }
}

try {
    $baseArgs = @(
        'DESIGNER',
        '/DisableStartupDialogs',
        '/DisableStartupMessages',
        '/IBConnectionString', $ConnectionString
    )
    if (-not [string]::IsNullOrWhiteSpace($UserName)) { $baseArgs += '/N'; $baseArgs += $UserName }
    if (-not [string]::IsNullOrEmpty($Password)) { $baseArgs += '/P'; $baseArgs += $Password }

    # 0) Сборка .cfe из xml (если -BuildFromXml)
    if ($BuildFromXml) {
        $cfeDir = [System.IO.Path]::GetDirectoryName($cfeFullPath)
        if ($cfeDir -and -not (Test-Path -LiteralPath $cfeDir -PathType Container)) {
            New-Item -ItemType Directory -Path $cfeDir -Force | Out-Null
        }
        $xmlFullPath = [System.IO.Path]::GetFullPath($XmlPath)
        $baseArgsOut = $baseArgs + @('/Out', $buildLoadLog)
        $loadXmlArgs = $baseArgsOut + @('/LoadConfigFromFiles', $xmlFullPath, '-Extension', $ExtensionName)
        Invoke-Platform -Arguments $loadXmlArgs -OperationName 'Сборка: загрузка расширения из XML в конфигурацию'
        $baseArgsDump = $baseArgs + @('/Out', $buildDumpLog)
        $dumpArgs = $baseArgsDump + @('/DumpCfg', $cfeFullPath, '-Extension', $ExtensionName)
        Invoke-Platform -Arguments $dumpArgs -OperationName 'Сборка: выгрузка расширения в .cfe'
    }

    $needLoad = -not $SkipLoadExtension -and $cfeFullPath
    $needUpdate = -not $SkipDbUpdate

    if ($needLoad -or $needUpdate) {
        $baseArgs += '/Out'; $baseArgs += $updateLog

        if ($needLoad) {
            $loadArgs = $baseArgs + @('/LoadCfg', $cfeFullPath, '-Extension', $ExtensionName)
            Invoke-Platform -Arguments $loadArgs -OperationName 'Загрузка расширения из .cfe в конфигурацию'
        }
        if ($needUpdate) {
            $updateArgs = $baseArgs + @('/UpdateDBCfg', '-Extension', $ExtensionName)
            Invoke-Platform -Arguments $updateArgs -OperationName 'Обновление конфигурации БД'
        }
    } else {
        Write-Host 'Пропуск: загрузка расширения и обновление БД отключены (флаги -SkipLoadExtension и -SkipDbUpdate).'
    }

    # Запуск 1С:Предприятие
    if (-not $SkipRunClient) {
        $enterpriseArgs = @(
            'ENTERPRISE',
            '/DisableStartupDialogs',
            '/DisableStartupMessages',
            '/IBConnectionString', $ConnectionString
        )
        if (-not [string]::IsNullOrWhiteSpace($UserName)) {
            $enterpriseArgs += '/N'
            $enterpriseArgs += $UserName
        }
        if (-not [string]::IsNullOrEmpty($Password)) {
            $enterpriseArgs += '/P'
            $enterpriseArgs += $Password
        }
        Invoke-Platform -Arguments $enterpriseArgs -OperationName 'Запуск 1С:Предприятие' -NoWait:(-not $Wait)
    } else {
        Write-Host 'Запуск клиента пропущен (флаг -SkipRunClient).'
    }

    $done = @()
    if ($BuildFromXml) { $done += 'собрано из xml' }
    if ($needLoad) { $done += 'загружено в конфигурацию' }
    if ($needUpdate) { $done += 'БД обновлена' }
    if (-not $SkipRunClient) { $done += 'клиент запущен' }
    Write-Host ('Готово: {0}.' -f ($done -join ', '))
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
