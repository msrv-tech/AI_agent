param(
    [string]$UserName = "codex",
    [string]$Password = $env:AI_AGENT_GUEST_PASSWORD,
    [string]$QemuGuestAgentMsiPath = "\\DEV1\D\bsl\tw\qga.msi"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

if ([string]::IsNullOrWhiteSpace($Password)) {
    throw "Set AI_AGENT_GUEST_PASSWORD or pass -Password explicitly."
}

$logDir = "C:\AIAgent"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logPath = Join-Path $logDir "guest_enable_management.log"

function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    $line | Tee-Object -FilePath $logPath -Append
}

function Ensure-LocalAdmin {
    param(
        [string]$UserName,
        [string]$Password
    )

    $existing = Get-LocalUser -Name $UserName -ErrorAction SilentlyContinue
    if (-not $existing) {
        Write-Log "Creating local user $UserName"
        net user $UserName $Password /add /y | Out-Null
    }
    else {
        Write-Log "Local user $UserName already exists"
    }

    Write-Log "Setting password for $UserName"
    net user $UserName $Password | Out-Null

    $groupMembers = net localgroup Administrators | Out-String
    if ($groupMembers -notmatch "(?im)^\s*$UserName\s*$") {
        Write-Log "Adding $UserName to local Administrators"
        net localgroup Administrators $UserName /add | Out-Null
    }
    else {
        Write-Log "$UserName is already in Administrators"
    }
}

function Configure-WinRm {
    Write-Log "Configuring WinRM"
    Enable-PSRemoting -Force -SkipNetworkProfileCheck
    winrm quickconfig -quiet | Out-Null
    Set-Service WinRM -StartupType Automatic
    Start-Service WinRM
    Set-Item WSMan:\localhost\Service\AllowUnencrypted $true
    Set-Item WSMan:\localhost\Service\Auth\Basic $true
    Set-Item WSMan:\localhost\Service\Auth\Negotiate $true
    Set-Item WSMan:\localhost\Service\Auth\Kerberos $true
    New-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" `
        -Name "LocalAccountTokenFilterPolicy" `
        -Value 1 `
        -PropertyType DWord `
        -Force | Out-Null
    netsh advfirewall firewall set rule group="Windows Remote Management" new enable=Yes | Out-Null
}

function Ensure-QemuGuestAgent {
    param([string]$MsiPath)

    if (Get-Service -Name qemu-ga -ErrorAction SilentlyContinue) {
        Write-Log "qemu-ga service already exists"
    }
    else {
        Write-Log "Installing qemu-ga from $MsiPath"
        $arguments = "/i `"$MsiPath`" /qn /norestart"
        $proc = Start-Process -FilePath msiexec.exe -ArgumentList $arguments -Wait -PassThru
        if ($proc.ExitCode -ne 0) {
            throw "msiexec exited with code $($proc.ExitCode)"
        }
    }

    Write-Log "Starting qemu-ga service"
    Set-Service qemu-ga -StartupType Automatic
    Start-Service qemu-ga
}

Write-Log "guest_enable_management.ps1 started"
Ensure-LocalAdmin -UserName $UserName -Password $Password
Configure-WinRm
Ensure-QemuGuestAgent -MsiPath $QemuGuestAgentMsiPath
Write-Log "guest_enable_management.ps1 completed"
