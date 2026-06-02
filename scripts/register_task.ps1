<#
.SYNOPSIS
  Register a Windows Scheduled Task that runs the trend pipeline every 30 minutes.

.DESCRIPTION
  This is the no-Docker way to "go live" on this Windows machine: the task runs the
  pipeline (RSS + Google Trends) with alerts enabled every 30 min, refreshing
  data/reports/latest.json. Run the dashboard separately with:
      python -m newsroom_trends.cli serve

.USAGE
  Right-click > Run with PowerShell, or:
      powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1
  Remove it with:
      Unregister-ScheduledTask -TaskName "NewsroomTrends" -Confirm:$false
#>

param(
    [int]$IntervalMinutes = 30,
    [string]$TaskName = "NewsroomTrends"
)

$ErrorActionPreference = "Stop"

# Resolve project root (parent of this script's folder) and a Python interpreter.
$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPython  = Join-Path $projectRoot ".venv\Scripts\python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { (Get-Command python).Source }

Write-Host "Project : $projectRoot"
Write-Host "Python  : $python"
Write-Host "Every   : $IntervalMinutes min"

$arguments = "-m newsroom_trends.cli -v run --only rss,google_trends --alert"

$action = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $projectRoot

# Repeat indefinitely starting now.
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopOnIdleEnd -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

# PYTHONUTF8 so Devanagari logs/reports don't choke on cp1252.
$env:PYTHONUTF8 = "1"

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description "Newsroom Hindi trend pipeline (every $IntervalMinutes min)" `
    -Force | Out-Null

Write-Host "`nRegistered scheduled task '$TaskName'. First run is immediate, then every $IntervalMinutes min."
Write-Host "View it:    Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "Run now:    Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Remove:     Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
