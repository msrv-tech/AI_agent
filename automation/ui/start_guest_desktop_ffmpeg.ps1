param(
    [string]$ComputerName = "192.168.2.130",
    [string]$UserName = "codex",
    [string]$Password = $env:AI_AGENT_GUEST_PASSWORD,
    [string]$TaskUser = "Admin",
    [string]$TaskPassword = $env:AI_AGENT_TASK_PASSWORD,
    [string]$PlatformExe = "C:\Tools\1cv8\8.5.1.1150\bin\1cv8.exe",
    [string]$BasePath = "",
    [string]$ShareRoot = "\\DEV1\D",
    [string]$ShareUser = "",
    [string]$SharePassword = "",
    [string]$TestCase = "standard",
    [string]$Prompt = "",
    [string]$DialogType = "Запрос1С",
    [string]$FollowupsJson = "[]",
    [switch]$ShowQueryBetweenTurns,
    [switch]$MouseControl,
    [string]$ExpectedText = "",
    [int]$RecordDurationSec = 0,
    [int]$RecordWidth = 1600,
    [int]$RecordHeight = 900,
    [int]$TimeoutSec = 360,
    [switch]$WindowsCompatible
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($Password)) {
    throw "Set AI_AGENT_GUEST_PASSWORD or pass -Password explicitly."
}
if ([string]::IsNullOrWhiteSpace($TaskPassword)) {
    throw "Set AI_AGENT_TASK_PASSWORD or pass -TaskPassword explicitly."
}
$env:PSModulePath = @(
    Join-Path $HOME "Documents\WindowsPowerShell\Modules"
    Join-Path $env:ProgramFiles "WindowsPowerShell\Modules"
    Join-Path $env:SystemRoot "system32\WindowsPowerShell\v1.0\Modules"
) -join ";"
Import-Module Microsoft.PowerShell.Security -ErrorAction Stop

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$securePassword = ConvertTo-SecureString $Password -AsPlainText -Force
$credential = New-Object System.Management.Automation.PSCredential($UserName, $securePassword)
$session = New-PSSession -ComputerName $ComputerName -Credential $credential -Authentication Basic
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$videoExtension = if ($WindowsCompatible.IsPresent) { "wmv" } else { "mp4" }
$guestVideoPath = "C:\AIAgent\videos\desktop_1c_ffmpeg_$stamp.$videoExtension"
$guestStdoutPath = "C:\AIAgent\desktop_1c_ffmpeg_stdout.log"
$defaultBaseSubPath = "bd\" + [string]([char]0x0423) + [string]([char]0x041D) + [string]([char]0x0424) + "3013238"

try {
    Copy-Item -ToSession $session -Path (Join-Path $repoRoot "automation\ui\ui_1c_agent_test.py") -Destination "C:\Work\AI_agent\automation\ui\ui_1c_agent_test.py" -Force
    Copy-Item -ToSession $session -Path (Join-Path $repoRoot "automation\ui\run_with_screen_recording.ps1") -Destination "C:\Work\AI_agent\automation\ui\run_with_screen_recording.ps1" -Force

    Invoke-Command -Session $session -ArgumentList $guestVideoPath, $guestStdoutPath, $PlatformExe, $BasePath, $ShareRoot, $ShareUser, $SharePassword, $defaultBaseSubPath, $TestCase, $Prompt, $DialogType, $FollowupsJson, $ShowQueryBetweenTurns.IsPresent, $MouseControl.IsPresent, $ExpectedText, $TimeoutSec, $RecordDurationSec, $RecordWidth, $RecordHeight, $TaskUser, $TaskPassword, $WindowsCompatible.IsPresent -ScriptBlock {
        param(
            [string]$VideoPath,
            [string]$StdoutPath,
            [string]$TargetPlatformExe,
            [string]$TargetBasePath,
            [string]$TargetShareRoot,
            [string]$TargetShareUser,
            [string]$TargetSharePassword,
            [string]$TargetDefaultBaseSubPath,
            [string]$TargetTestCase,
            [string]$TargetPrompt,
            [string]$TargetDialogType,
            [string]$TargetFollowupsJson,
            [bool]$TargetShowQueryBetweenTurns,
            [bool]$TargetMouseControl,
            [string]$TargetExpectedText,
            [int]$TargetTestTimeoutSec,
            [int]$TargetRecordDurationSec,
            [int]$TargetRecordWidth,
            [int]$TargetRecordHeight,
            [string]$TargetTaskUser,
            [string]$TargetTaskPassword,
            [bool]$TargetWindowsCompatible
        )

        $ErrorActionPreference = "Stop"
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $VideoPath) | Out-Null
        Remove-Item $StdoutPath -Force -ErrorAction SilentlyContinue
        Remove-Item C:\AIAgent\desktop_1c_test.log -Force -ErrorAction SilentlyContinue
        Remove-Item C:\AIAgent\desktop_1c_startup.log -Force -ErrorAction SilentlyContinue
        Remove-Item C:\AIAgent\desktop_1c_record_start.marker -Force -ErrorAction SilentlyContinue
        Remove-Item C:\AIAgent\desktop_1c_artifacts\* -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item C:\Work\AI_agent\automation\ui\__pycache__ -Recurse -Force -ErrorAction SilentlyContinue
        Get-Process 1cv8,1cv8c,1cv8s -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

        if ([string]::IsNullOrWhiteSpace($TargetBasePath)) {
            $TargetBasePath = Join-Path $TargetShareRoot $TargetDefaultBaseSubPath
        }

        $shareLog = "C:\AIAgent\desktop_1c_share_access.log"
        Remove-Item $shareLog -Force -ErrorAction SilentlyContinue
        "ShareRoot=$TargetShareRoot" | Out-File $shareLog -Encoding UTF8 -Append
        "BasePath=$TargetBasePath" | Out-File $shareLog -Encoding UTF8 -Append
        $previousPreference = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        cmd.exe /c "net use $TargetShareRoot /delete /y" *> $null
        $ErrorActionPreference = $previousPreference
        if (-not [string]::IsNullOrWhiteSpace($TargetShareUser)) {
            $netUseCommand = "net use $TargetShareRoot /user:$TargetShareUser $TargetSharePassword"
            $previousPreference = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            cmd.exe /c $netUseCommand 2>&1 | Out-File $shareLog -Encoding UTF8 -Append
            $ErrorActionPreference = $previousPreference
        }
        try {
            "BasePathExists=$(Test-Path $TargetBasePath)" | Out-File $shareLog -Encoding UTF8 -Append
        }
        catch {
            "BasePathExistsError=$($_.Exception.Message)" | Out-File $shareLog -Encoding UTF8 -Append
        }

        Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Win32Window {
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@ -ErrorAction SilentlyContinue
        Get-Process cmd -ErrorAction SilentlyContinue | ForEach-Object {
            if ($_.MainWindowHandle -ne 0) {
                [Win32Window]::ShowWindow($_.MainWindowHandle, 6) | Out-Null
            }
        }
        Get-Process WindowsTerminal,OpenConsole -ErrorAction SilentlyContinue | ForEach-Object {
            if ($_.SessionId -eq 1) {
                try { $_.CloseMainWindow() | Out-Null } catch {}
                Start-Sleep -Milliseconds 300
                if (-not $_.HasExited) {
                    try { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue } catch {}
                }
            }
        }

        function ConvertTo-PsSingleQuotedLiteral([string]$Value) {
            return ("'" + $Value.Replace("'", "''") + "'")
        }

        $followupsJsonBase64 = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($TargetFollowupsJson))
        $showQueryBetweenTurnsLiteral = if ($TargetShowQueryBetweenTurns) { '$true' } else { '$false' }
        $mouseControlLiteral = if ($TargetMouseControl) { '$true' } else { '$false' }
        $innerScriptPath = "C:\AIAgent\run_desktop_1c_ffmpeg_inner.ps1"
        @(
            '$ErrorActionPreference = "Continue"',
            'Set-Location C:\Work\AI_agent',
            'Get-Process WindowsTerminal,OpenConsole,cmd -ErrorAction SilentlyContinue | Where-Object { $_.SessionId -eq (Get-Process -Id $PID).SessionId -and $_.Id -ne $PID } | Stop-Process -Force -ErrorAction SilentlyContinue',
            '$shareLog = "C:\AIAgent\desktop_1c_share_access.log"',
            '$targetShareRoot = ' + (ConvertTo-PsSingleQuotedLiteral $TargetShareRoot),
            '$targetBasePath = ' + (ConvertTo-PsSingleQuotedLiteral $TargetBasePath),
            '$targetShareUser = ' + (ConvertTo-PsSingleQuotedLiteral $TargetShareUser),
            '$targetSharePassword = ' + (ConvertTo-PsSingleQuotedLiteral $TargetSharePassword),
            '$followupsPath = "C:\AIAgent\desktop_1c_followups.json"',
            '$followupsB64 = ''' + $followupsJsonBase64 + '''',
            '[System.IO.File]::WriteAllBytes($followupsPath, [Convert]::FromBase64String($followupsB64))',
            'Remove-Item C:\Work\AI_agent\automation\ui\__pycache__ -Recurse -Force -ErrorAction SilentlyContinue',
            '"TaskShareRoot=$targetShareRoot" | Out-File $shareLog -Encoding UTF8 -Append',
            '"TaskBasePath=$targetBasePath" | Out-File $shareLog -Encoding UTF8 -Append',
            'cmd.exe /c "net use ""$targetShareRoot"" /delete /y >nul 2>nul"',
            'if (-not [string]::IsNullOrWhiteSpace($targetShareUser)) { cmd.exe /c "net use ""$targetShareRoot"" /user:""$targetShareUser"" ""$targetSharePassword""" 2>&1 | Out-File $shareLog -Encoding UTF8 -Append }',
            '"TaskBasePathExists=$(Test-Path $targetBasePath)" | Out-File $shareLog -Encoding UTF8 -Append',
            '$testArgs = @(',
            '    "automation\ui\ui_1c_agent_test.py",',
            "    `"--platform-exe`", `"$TargetPlatformExe`",",
            "    `"--base-path`", `"$TargetBasePath`",",
            "    `"--test-case`", `"$TargetTestCase`",",
            '    "--dialog-type", ' + (ConvertTo-PsSingleQuotedLiteral $TargetDialogType) + ',',
            '    "--timeout-sec", ' + (ConvertTo-PsSingleQuotedLiteral ([string]$TargetTestTimeoutSec)) + ',',
            '    "--startup-timeout-sec", "120",',
            '    "--backend", "uia",',
            '    "--log-file", "C:\AIAgent\desktop_1c_test.log",',
            '    "--screenshot-dir", "C:\AIAgent\desktop_1c_artifacts",',
            '    "--record-start-marker", "C:\AIAgent\desktop_1c_record_start.marker",',
            '    "--followups-file", $followupsPath',
            ')',
            'if (' + $showQueryBetweenTurnsLiteral + ') { $testArgs += @("--show-query-between-turns") }',
            'if (' + $mouseControlLiteral + ') { $testArgs += @("--mouse-control") }',
            'if (-not [string]::IsNullOrWhiteSpace(' + (ConvertTo-PsSingleQuotedLiteral $TargetPrompt) + ')) { $testArgs += @("--prompt", ' + (ConvertTo-PsSingleQuotedLiteral $TargetPrompt) + ') }',
            'if (-not [string]::IsNullOrWhiteSpace(' + (ConvertTo-PsSingleQuotedLiteral $TargetExpectedText) + ')) { $testArgs += @("--expected-text", ' + (ConvertTo-PsSingleQuotedLiteral $TargetExpectedText) + ') }',
            '$testArgs | Out-File C:\AIAgent\desktop_1c_args.txt -Encoding UTF8',
            '& C:\Python\python.exe @testArgs *> C:\AIAgent\desktop_1c_ffmpeg_inner_stdout.log',
            'exit $LASTEXITCODE'
        ) | Set-Content -Path $innerScriptPath -Encoding UTF8

        $scriptPath = "C:\AIAgent\run_desktop_1c_ffmpeg.ps1"
        $recordArgs = ""
        if ($TargetRecordWidth -gt 0 -and $TargetRecordHeight -gt 0) {
            $recordArgs += " -Width $TargetRecordWidth -Height $TargetRecordHeight"
        }
        if ($TargetRecordDurationSec -gt 0) {
            $recordArgs += " -FixedDurationSec $TargetRecordDurationSec"
        }
        if ($TargetWindowsCompatible) {
            $recordArgs += " -WindowsCompatible"
        }
        $recordArgs += " -StartMarkerPath `"C:\AIAgent\desktop_1c_record_start.marker`" -StartMarkerTimeoutSec 240"
        @(
            '$ErrorActionPreference = "Continue"',
            "Set-Location C:\Work\AI_agent",
            "& C:\Work\AI_agent\automation\ui\run_with_screen_recording.ps1 -VideoPath `"$VideoPath`" -FfmpegPath `"C:\Tools\ffmpeg\bin\ffmpeg.exe`" -Framerate 12$recordArgs -ExecutablePath `"powershell.exe`" -ExecutableArguments `"-NoProfile -ExecutionPolicy Bypass -File `"`"$innerScriptPath`"`"`" *> `"$StdoutPath`"",
            'exit $LASTEXITCODE'
        ) | Set-Content -Path $scriptPath -Encoding UTF8

        $taskName = "AI Desktop 1C FFmpeg"
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
        $taskCommand = "powershell.exe -WindowStyle Hidden -NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""
        $taskStdout = "C:\AIAgent\schtasks_create_stdout.log"
        $taskStderr = "C:\AIAgent\schtasks_create_stderr.log"
        Remove-Item $taskStdout, $taskStderr -Force -ErrorAction SilentlyContinue
        $createArgs = "/Create /TN `"$taskName`" /SC ONCE /ST 23:59 /TR `"$taskCommand`" /RU `"$TargetTaskUser`" /RP `"$TargetTaskPassword`" /RL HIGHEST /IT /F"
        Start-Process -FilePath "schtasks.exe" -ArgumentList $createArgs -WindowStyle Hidden -Wait -RedirectStandardOutput $taskStdout -RedirectStandardError $taskStderr
        $runArgs = "/Run /TN `"$taskName`""
        Start-Process -FilePath "schtasks.exe" -ArgumentList $runArgs -WindowStyle Hidden -Wait -RedirectStandardOutput "C:\AIAgent\schtasks_run_stdout.log" -RedirectStandardError "C:\AIAgent\schtasks_run_stderr.log"
    }

    $runSubmittedAt = Get-Date
    $deadline = $runSubmittedAt.AddSeconds($TimeoutSec + 300)
    do {
        Start-Sleep -Seconds 5
        $state = Invoke-Command -Session $session -ScriptBlock {
            $task = Get-ScheduledTask -TaskName "AI Desktop 1C FFmpeg" -ErrorAction SilentlyContinue
            $info = if ($task) { Get-ScheduledTaskInfo -TaskName "AI Desktop 1C FFmpeg" } else { $null }
            [pscustomobject]@{
                State = if ($task) { [string]$task.State } else { "Missing" }
                LastTaskResult = if ($info) { [int64]$info.LastTaskResult } else { $null }
                LastRunTime = if ($info) { [datetime]$info.LastRunTime } else { [datetime]::MinValue }
            }
        }
        $taskStartedThisRun = $state.LastRunTime -ge $runSubmittedAt.AddSeconds(-2)
        if ($taskStartedThisRun -and $state.State -ne "Running" -and $state.LastTaskResult -ne 267009) {
            break
        }
    } while ((Get-Date) -lt $deadline)

    $hostDir = Join-Path $repoRoot "automation\logs\videos_ffmpeg_desktop\$stamp"
    New-Item -ItemType Directory -Force -Path $hostDir | Out-Null
    Copy-Item -FromSession $session -Path $guestVideoPath -Destination (Join-Path $hostDir "desktop_1c_ffmpeg.$videoExtension") -Force -ErrorAction SilentlyContinue
    Copy-Item -FromSession $session -Path "$guestVideoPath.ffmpeg.log" -Destination (Join-Path $hostDir "desktop_1c_ffmpeg.$videoExtension.ffmpeg.log") -Force -ErrorAction SilentlyContinue
    Copy-Item -FromSession $session -Path $guestStdoutPath -Destination (Join-Path $hostDir "desktop_1c_ffmpeg_stdout.log") -Force -ErrorAction SilentlyContinue
    Copy-Item -FromSession $session -Path "C:\AIAgent\desktop_1c_ffmpeg_inner_stdout.log" -Destination (Join-Path $hostDir "desktop_1c_ffmpeg_inner_stdout.log") -Force -ErrorAction SilentlyContinue
    Copy-Item -FromSession $session -Path "C:\AIAgent\desktop_1c_test.log" -Destination (Join-Path $hostDir "desktop_1c_test.log") -Force -ErrorAction SilentlyContinue
    Copy-Item -FromSession $session -Path "C:\AIAgent\desktop_1c_startup.log" -Destination (Join-Path $hostDir "desktop_1c_startup.log") -Force -ErrorAction SilentlyContinue
    Copy-Item -FromSession $session -Path "C:\AIAgent\desktop_1c_share_access.log" -Destination (Join-Path $hostDir "desktop_1c_share_access.log") -Force -ErrorAction SilentlyContinue
    Copy-Item -FromSession $session -Path "C:\AIAgent\schtasks_*.log" -Destination $hostDir -Force -ErrorAction SilentlyContinue
    Copy-Item -FromSession $session -Path "C:\AIAgent\desktop_1c_artifacts" -Destination (Join-Path $hostDir "artifacts") -Recurse -Force -ErrorAction SilentlyContinue

    Write-Host "Video: $(Join-Path $hostDir "desktop_1c_ffmpeg.$videoExtension")"
    Write-Host "Guest video: $guestVideoPath"
    Write-Host "Task result: $($state.LastTaskResult)"
    if ($state.LastTaskResult -eq 0) {
        exit 0
    }
    exit 1
}
finally {
    Remove-PSSession $session
}
