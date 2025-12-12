[CmdletBinding()]
param(
    [string]$PlatformExe = 'C:\Program Files\1cv8\8.3.27.1859\bin\1cv8.exe',
    [string]$ConnectionString = 'File="D:\EDT_base\КонфигурацияТест";',
    [string]$UserName = '',
    [string]$Password = '',
    [string]$LogDir = "$PSScriptRoot\logs",
    [string]$VanessaRunnerEpf = "$PSScriptRoot\vanessa-automation-single.epf",
    [string]$FeatureFile = "$PSScriptRoot\AddCatalog2TestEntry.feature",
    [string]$VAParamsPath = "$PSScriptRoot\VAParams.json",
    [switch]$SkipDbUpdate
)

<# 
.SYNOPSIS
Обновляет конфигурацию БД через 1С:Предприятие и запускает сценарий Vanessa Automation,
который открывает Справочник2 и создает тестовую запись.

.EXAMPLE
.\update-and-run-vanessa.ps1 `
    -ConnectionString 'File="D:\EDT_base\test1";' `
    -UserName 'tech' -Password 'secret'

Скрипт предполагает, что все нужные артефакты (epf, feature, VAParams) лежат рядом в текущей папке.
#>

$ErrorActionPreference = 'Stop'

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

function Invoke-Platform {
    param(
        [Parameter(Mandatory)]
        [string[]]$Arguments,
        [Parameter(Mandatory)]
        [string]$OperationName
    )

    Write-Host "==> $OperationName"
    Write-Host ("    1cv8.exe {0}" -f ($Arguments -join ' '))

    $process = Start-Process -FilePath $PlatformExe -ArgumentList $Arguments -PassThru -Wait
    if ($process.ExitCode -ne 0) {
        throw "Команда 1cv8 для операции '$OperationName' завершилась с кодом $($process.ExitCode)"
    }
}

function Initialize-VAParamsFile {
    param(
        [Parameter(Mandatory)]
        [string]$Path,
        [Parameter(Mandatory)]
        [string]$FeatureFilePath,
        [Parameter(Mandatory)]
        [string]$ConnectionStringValue
    )

    $directory = Split-Path -Parent $Path
    if ($directory -and -not (Test-Path -LiteralPath $directory)) {
        New-Item -ItemType Directory -Path $directory | Out-Null
    }

    $template = [ordered]@{
        Lang                  = 'ru'
        featurepath           = $FeatureFilePath
        'ВыполнитьСценарии'   = $true
        useaddin              = $true
        TestClient            = @{
            runtestclientwithmaximizedwindow = $true
            datatestclients = @(
                [ordered]@{
                    Name                 = 'LocalFileBase'
                    PathToInfobase       = $ConnectionStringValue
                    PortTestClient       = 48010
                    AddItionalParameters = ''
                    ClientType           = 'Thin'
                    ComputerName         = 'localhost'
                }
            )
        }
    }

    $json = $template | ConvertTo-Json -Depth 5
    $json | Set-Content -LiteralPath $Path -Encoding utf8
}

function Set-JsonPropertyValue {
    param(
        [Parameter(Mandatory)]
        $Object,
        [Parameter(Mandatory)]
        [string]$Name,
        $Value
    )

    $prop = $Object.PSObject.Properties[$Name]
    if ($prop) {
        $prop.Value = $Value
    } else {
        $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
    }
}

Test-RequiredFile -Path $PlatformExe -Description 'платформы 1cv8'
Test-RequiredFile -Path $VanessaRunnerEpf -Description 'Vanessa Automation (epf)'
Test-RequiredFile -Path $FeatureFile -Description 'Vanessa Automation feature'

$vanessaRunnerEpfFullPath = (Resolve-Path -LiteralPath $VanessaRunnerEpf).Path
$featureFullPath = (Resolve-Path -LiteralPath $FeatureFile).Path

if (-not (Test-Path -LiteralPath $VAParamsPath)) {
    Write-Host "Создаю файл VAParams.json по умолчанию: $VAParamsPath"
    Initialize-VAParamsFile -Path $VAParamsPath -FeatureFilePath $featureFullPath -ConnectionStringValue $ConnectionString
}

Test-RequiredFile -Path $VAParamsPath -Description 'VAParams.json'
$vaParamsFullPath = (Resolve-Path -LiteralPath $VAParamsPath).Path

try {
    $vaParams = Get-Content -LiteralPath $vaParamsFullPath -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop
} catch {
    throw "Не удалось прочитать VAParams.json: $($_.Exception.Message)"
}

if ($null -eq $vaParams) {
    throw "Не удалось загрузить структуру настроек из VAParams.json"
}

Set-JsonPropertyValue -Object $vaParams -Name 'featurepath' -Value $featureFullPath
Set-JsonPropertyValue -Object $vaParams -Name 'ВыполнитьСценарии' -Value $true
Set-JsonPropertyValue -Object $vaParams -Name 'useaddin' -Value $true

if ($null -eq $vaParams.TestClient) {
    $vaParams | Add-Member -NotePropertyName 'TestClient' -NotePropertyValue ([pscustomobject]@{})
}

$testClient = $vaParams.TestClient
Set-JsonPropertyValue -Object $testClient -Name 'runtestclientwithmaximizedwindow' -Value $true

if ($null -eq $testClient.datatestclients -or $testClient.datatestclients.Count -eq 0) {
    $testClient.datatestclients = @()
}

$clientSettings = [pscustomobject]@{
    Name                 = 'LocalFileBase'
    PathToInfobase       = $ConnectionString
    PortTestClient       = 48010
    AddItionalParameters = ''
    ClientType           = 'Thin'
    ComputerName         = 'localhost'
}

if ($testClient.datatestclients.Count -eq 0) {
    $testClient.datatestclients += $clientSettings
} else {
    $testClient.datatestclients[0] = $clientSettings
}

$vaParams | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $vaParamsFullPath -Encoding utf8

if (-not (Test-Path -LiteralPath $LogDir)) {
    Write-Host "Создаю каталог логов: $LogDir"
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

$updateLog = Join-Path -Path $LogDir -ChildPath 'update-db.log'
$vanessaLog = Join-Path -Path $LogDir -ChildPath 'vanessa.log'

if (-not $SkipDbUpdate) {
    $designerArgs = @(
        'DESIGNER',
        '/DisableStartupDialogs',
        '/DisableStartupMessages',
        '/IBConnectionString', $ConnectionString
    )

    if (-not [string]::IsNullOrWhiteSpace($UserName)) {
        $designerArgs += '/N'
        $designerArgs += $UserName
    }
    if (-not [string]::IsNullOrEmpty($Password)) {
        $designerArgs += '/P'
        $designerArgs += $Password
    }

    $designerArgs += '/Out'
    $designerArgs += $updateLog
    $designerArgs += '/UpdateDBCfg'

    Invoke-Platform -Arguments $designerArgs -OperationName 'Обновление конфигурации БД'
} else {
    Write-Host 'Пропускаю обновление БД (флаг -SkipDbUpdate).'
}

$vanessaCommand = "StartFeaturePlayer;FeatureFile=$featureFullPath;CloseTestClientBefore=1;StopOnError=1;LogDirectory=$LogDir;VAParams=$vaParamsFullPath;vanessarun=1;"

$vanessaArgs = @(
    'ENTERPRISE',
    '/DisableStartupDialogs',
    '/DisableStartupMessages',
    '/TESTMANAGER',
    '/IBConnectionString', $ConnectionString
)

if (-not [string]::IsNullOrWhiteSpace($UserName)) {
    $vanessaArgs += '/N'
    $vanessaArgs += $UserName
}
if (-not [string]::IsNullOrEmpty($Password)) {
    $vanessaArgs += '/P'
    $vanessaArgs += $Password
}

$vanessaArgs += '/Execute'
$vanessaArgs += $vanessaRunnerEpfFullPath
$vanessaArgs += '/Out'
$vanessaArgs += $vanessaLog
$vanessaArgs += '/C'
$vanessaArgs += $vanessaCommand

Invoke-Platform -Arguments $vanessaArgs -OperationName 'Запуск сценария Vanessa Automation'

Write-Host 'Выполнение завершено: обновление БД и сценарий Vanessa успешно отработали.'

