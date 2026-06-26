param(
    [string]$TaskName = "BTCQuantDemoSupervisor",
    [string]$ProjectDir = (Resolve-Path "$PSScriptRoot\..\..").Path,
    [int]$IntervalMinutes = 15
)

$PythonExe = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$ScriptPath = Join-Path $ProjectDir "scripts\run_demo_service.py"
if (!(Test-Path $PythonExe)) {
    Write-Error "Virtual environment not found: $PythonExe"
    exit 1
}
if (!(Test-Path $ScriptPath)) {
    Write-Error "Script not found: $ScriptPath"
    exit 1
}

$Action = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$ScriptPath`" --max-iterations 1" -WorkingDirectory $ProjectDir
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) -RepetitionDuration (New-TimeSpan -Days 3650)
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "BTC Quant Framework V1.0 Demo supervisor" -Force
Write-Host "Created/updated scheduled task: $TaskName"
Write-Host "ProjectDir: $ProjectDir"
Write-Host "Interval: every $IntervalMinutes minutes"
