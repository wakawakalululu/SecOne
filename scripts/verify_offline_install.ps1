#requires -Version 5.1
<#
End-to-end acceptance harness for the SecOne Windows installer.

Runs, in one command:
  1. sanity checks on the installer file
  2. silent install to an isolated temp directory (desktop shortcut task)
  3. installed EXE hash comparison with dist\SecOne\SecOne.exe
  4. shortcut target / working directory resolution
  5. first launch through the shortcut with a reduced PATH and no Python
  6. optional model package deployment + presence check
  7. silent uninstall, verifying shortcut removal and user data retention
  8. JSON report with per-step DONE / FAILED / SKIPPED

Intended for a clean Windows machine without Python or network. Running it on
a build machine proves the harness works, not the clean-machine acceptance.
Pass -CleanMachine on the clean host so the report records that declaration.
#>
[CmdletBinding()]
param(
    [string]$Installer = "dist\installer\SecOne-1.0.0-rc1-setup.exe",
    [string]$InstallDir = "",
    [string]$ModelPackage = "",
    [string]$JsonOut = "artifacts\offline_install_report.json",
    [int]$StartupSeconds = 12,
    [switch]$CleanMachine,
    [switch]$KeepInstall
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$steps = New-Object System.Collections.ArrayList

function Add-Step {
    param([string]$Name, [string]$Status, [string]$Detail, [double]$Seconds = 0)
    [void]$steps.Add([ordered]@{
        name    = $Name
        status  = $Status
        detail  = $Detail
        seconds = [math]::Round($Seconds, 2)
    })
    $color = switch ($Status) { "DONE" { "Green" } "FAILED" { "Red" } default { "Yellow" } }
    Write-Host ("[{0}] {1} - {2}" -f $Status, $Name, $Detail) -ForegroundColor $color
}

function Resolve-RepoPath([string]$Path) {
    if ([IO.Path]::IsPathRooted($Path)) { return [IO.Path]::GetFullPath($Path) }
    return [IO.Path]::GetFullPath((Join-Path $repoRoot $Path))
}

function Get-Sha256([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

$installerPath = Resolve-RepoPath $Installer
$reportPath = Resolve-RepoPath $JsonOut
$referenceExe = Join-Path $repoRoot "dist\SecOne\SecOne.exe"
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "SecOne.lnk"
$uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{8E2B7E1C-5C4A-4B1E-9F61-2D3A4C5B6D70}_is1"
$createdInstallDir = $false
$uninstalled = $false

if ([string]::IsNullOrWhiteSpace($InstallDir)) {
    $InstallDir = Join-Path $env:TEMP ("secone-accept-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
}

$envInfo = [ordered]@{
    os           = (Get-CimInstance Win32_OperatingSystem).Caption + " " + [Environment]::OSVersion.Version.ToString()
    powershell   = $PSVersionTable.PSVersion.ToString()
    user         = [Environment]::UserName
    elevated     = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    python_on_path = @(Get-Command python, python3, py -ErrorAction SilentlyContinue | ForEach-Object { $_.Source })
    clean_machine_declared = [bool]$CleanMachine
    install_dir  = $InstallDir
    started_at   = (Get-Date).ToString("o")
}

Write-Host "SecOne offline install acceptance" -ForegroundColor Cyan
Write-Host ("installer : {0}" -f $installerPath)
Write-Host ("install   : {0}" -f $InstallDir)

try {
    # --- 1. installer sanity -------------------------------------------------
    $t0 = Get-Date
    if (-not (Test-Path -LiteralPath $installerPath)) { throw "Installer not found: $installerPath" }
    $installerInfo = Get-Item -LiteralPath $installerPath
    $installerHash = Get-Sha256 $installerPath
    Add-Step "installer_present" "DONE" ("{0} bytes, sha256={1}" -f $installerInfo.Length, $installerHash) ((Get-Date) - $t0).TotalSeconds

    if ($envInfo.python_on_path.Count -gt 0) {
        $pc = if ($CleanMachine) { "FAILED" } else { "SKIPPED" }
        Add-Step "clean_machine_precondition" $pc ("python found on PATH: " + ($envInfo.python_on_path -join "; "))
    } else {
        Add-Step "clean_machine_precondition" "DONE" "no python/python3/py on PATH"
    }

    if (Test-Path -LiteralPath $shortcutPath) {
        Add-Step "desktop_shortcut_precondition" "FAILED" "A SecOne.lnk already exists on the desktop; aborting so it is not overwritten"
        throw "pre-existing desktop shortcut"
    }

    # --- 2. silent install ---------------------------------------------------
    $t0 = Get-Date
    $logPath = Join-Path $env:TEMP ("secone-install-" + [guid]::NewGuid().ToString("N").Substring(0, 8) + ".log")
    $installArgs = @(
        "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
        "/MERGETASKS=desktopicon",
        "/DIR=`"$InstallDir`"",
        "/LOG=`"$logPath`""
    )
    $setup = Start-Process -FilePath $installerPath -ArgumentList $installArgs -Wait -PassThru
    if ($setup.ExitCode -ne 0) { throw "installer exit code $($setup.ExitCode) (see $logPath)" }
    $installSeconds = ((Get-Date) - $t0).TotalSeconds
    $createdInstallDir = $true
    $fileCount = @(Get-ChildItem -LiteralPath $InstallDir -Recurse -File).Count
    Add-Step "silent_install" "DONE" ("exit 0, {0} files, log {1}" -f $fileCount, $logPath) $installSeconds

    # --- 3. payload integrity ------------------------------------------------
    $t0 = Get-Date
    $installedExe = Join-Path $InstallDir "SecOne.exe"
    if (-not (Test-Path -LiteralPath $installedExe)) { throw "SecOne.exe missing after install" }
    $installedHash = Get-Sha256 $installedExe
    if (Test-Path -LiteralPath $referenceExe) {
        $referenceHash = Get-Sha256 $referenceExe
        if ($installedHash -ne $referenceHash) { throw "installed SecOne.exe hash $installedHash != reference $referenceHash" }
        Add-Step "payload_hash" "DONE" ("SecOne.exe {0} == dist\SecOne\SecOne.exe {1}" -f $installedHash, $referenceHash) ((Get-Date) - $t0).TotalSeconds
    } else {
        Add-Step "payload_hash" "SKIPPED" ("reference EXE absent; installed hash {0}" -f $installedHash) ((Get-Date) - $t0).TotalSeconds
    }

    if (-not (Test-Path -LiteralPath $uninstallKey)) { throw "uninstall registry entry missing: $uninstallKey" }
    Add-Step "uninstall_registration" "DONE" $uninstallKey

    # --- 4. shortcut ---------------------------------------------------------
    $t0 = Get-Date
    if (-not (Test-Path -LiteralPath $shortcutPath)) { throw "desktop shortcut missing: $shortcutPath" }
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($shortcutPath)
    $lnkTarget = [IO.Path]::GetFullPath($lnk.TargetPath)
    $lnkWorkDir = [IO.Path]::GetFullPath($lnk.WorkingDirectory)
    $expectedExe = [IO.Path]::GetFullPath($installedExe)
    if ($lnkTarget -ne $expectedExe) { throw "shortcut target $lnkTarget != $expectedExe" }
    Add-Step "desktop_shortcut" "DONE" ("{0} bytes, target={1}, workdir={2}" -f (Get-Item -LiteralPath $shortcutPath).Length, $lnkTarget, $lnkWorkDir) ((Get-Date) - $t0).TotalSeconds

    # --- 5. first launch through the shortcut --------------------------------
    $t0 = Get-Date
    $savedPath = $env:PATH
    $savedHome = $env:PYTHONHOME
    $savedPythonPath = $env:PYTHONPATH
    $savedQpa = $env:QT_QPA_PLATFORM
    try {
        $env:PATH = "$env:SystemRoot\system32;$env:SystemRoot"
        Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
        Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
        $env:QT_QPA_PLATFORM = "offscreen"

        $launched = Start-Process -FilePath $shortcutPath -PassThru
        Start-Sleep -Seconds $StartupSeconds
        $app = @(Get-Process -Name "SecOne" -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $expectedExe })
        if ($app.Count -ne 1) { throw "SecOne.exe from $expectedExe is not running after ${StartupSeconds}s" }

        $historyDb = Join-Path $InstallDir "data\history.db"
        $appLog = Join-Path $InstallDir "logs\secone.log"
        if (-not (Test-Path -LiteralPath $historyDb)) { throw "first run did not create data\history.db" }
        if (-not (Test-Path -LiteralPath $appLog)) { throw "first run did not create logs\secone.log" }
        $logText = Get-Content -LiteralPath $appLog -Raw
        if ($logText -notmatch "started") { throw "log does not contain a startup record" }
        Add-Step "launch_via_shortcut" "DONE" ("alive {0}s with PATH={1}, created data\history.db + logs\secone.log" -f $StartupSeconds, $env:PATH) ((Get-Date) - $t0).TotalSeconds
    } finally {
        $env:PATH = $savedPath
        if ($null -ne $savedHome) { $env:PYTHONHOME = $savedHome } else { Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue }
        if ($null -ne $savedPythonPath) { $env:PYTHONPATH = $savedPythonPath } else { Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue }
        if ($null -ne $savedQpa) { $env:QT_QPA_PLATFORM = $savedQpa } else { Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue }
        Get-Process -Name "SecOne" -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $expectedExe } | Stop-Process -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }

    # --- 6. optional model package ------------------------------------------
    $t0 = Get-Date
    if ([string]::IsNullOrWhiteSpace($ModelPackage)) {
        Add-Step "model_package" "SKIPPED" "no -ModelPackage given (model is delivered separately)"
    } else {
        $modelZip = Resolve-RepoPath $ModelPackage
        if (-not (Test-Path -LiteralPath $modelZip)) { throw "model package not found: $modelZip" }
        Expand-Archive -LiteralPath $modelZip -DestinationPath $InstallDir -Force
        $gguf = @(Get-ChildItem -LiteralPath (Join-Path $InstallDir "models") -Filter "*.gguf" -File -ErrorAction SilentlyContinue)
        $server = Join-Path $InstallDir "runtime\llama-server.exe"
        if ($gguf.Count -eq 0) { throw "model package did not provide models\*.gguf" }
        if (-not (Test-Path -LiteralPath $server)) { throw "model package did not provide runtime\llama-server.exe" }
        Add-Step "model_package" "DONE" ("{0} gguf ({1} bytes), runtime\llama-server.exe present" -f $gguf.Count, $gguf[0].Length) ((Get-Date) - $t0).TotalSeconds
    }

    # --- 7. uninstall and data retention ------------------------------------
    $t0 = Get-Date
    $uninstaller = Join-Path $InstallDir "unins000.exe"
    if (-not (Test-Path -LiteralPath $uninstaller)) { throw "uninstaller missing: $uninstaller" }
    $uninstall = Start-Process -FilePath $uninstaller -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") -Wait -PassThru
    if ($uninstall.ExitCode -ne 0) { throw "uninstaller exit code $($uninstall.ExitCode)" }
    $uninstalled = $true
    Start-Sleep -Seconds 2
    if (Test-Path -LiteralPath $installedExe) { throw "SecOne.exe still present after uninstall" }
    if (Test-Path -LiteralPath $shortcutPath) { throw "desktop shortcut still present after uninstall" }
    if (Test-Path -LiteralPath $uninstallKey) { throw "uninstall registry entry still present" }
    if (-not (Test-Path -LiteralPath (Join-Path $InstallDir "data\history.db"))) { throw "user data data\history.db was removed by uninstall" }
    if (-not (Test-Path -LiteralPath (Join-Path $InstallDir "logs"))) { throw "logs directory was removed by uninstall" }
    Add-Step "silent_uninstall" "DONE" "program files, shortcut and registry entry removed; data\ and logs\ retained" ((Get-Date) - $t0).TotalSeconds
}
catch {
    Add-Step "harness_error" "FAILED" $_.Exception.Message
}
finally {
    if ($createdInstallDir -and -not $KeepInstall) {
        if (-not $uninstalled -and (Test-Path -LiteralPath (Join-Path $InstallDir "unins000.exe"))) {
            Start-Process -FilePath (Join-Path $InstallDir "unins000.exe") -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") -Wait -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2
        }
        Get-Process -Name "SecOne" -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$InstallDir*" } | Stop-Process -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    if ($KeepInstall) { Write-Host ("kept install dir: {0}" -f $InstallDir) -ForegroundColor Yellow }

    $failed = @($steps | Where-Object { $_.status -eq "FAILED" })
    $report = [ordered]@{
        result        = if ($failed.Count -eq 0) { "DONE" } else { "FAILED" }
        scope         = if ($CleanMachine) { "clean-windows" } else { "acceptance-harness-run" }
        note          = if ($CleanMachine) { "Executed on a host declared clean by the operator." } else { "Harness executed off the clean-machine path; this run validates the harness, not clean-machine acceptance." }
        finished_at   = (Get-Date).ToString("o")
        environment   = $envInfo
        installer     = [ordered]@{ path = $installerPath; size = $installerInfo.Length; sha256 = $installerHash }
        steps         = $steps
    }
    $reportDir = Split-Path -Parent $reportPath
    if ($reportDir -and -not (Test-Path -LiteralPath $reportDir)) { New-Item -ItemType Directory -Path $reportDir -Force | Out-Null }
    $json = ($report | ConvertTo-Json -Depth 8)
    [IO.File]::WriteAllText($reportPath, $json, (New-Object Text.UTF8Encoding($false)))
    Write-Host ("report: {0} -> {1}" -f $report.result, $reportPath) -ForegroundColor Cyan
    if ($failed.Count -gt 0) { exit 1 } else { exit 0 }
}
