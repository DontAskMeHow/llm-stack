# Регистрация задачи Планировщика для релея: запуск при входе, без консольного окна,
# без ограничения времени, повторные входы не плодят копии.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File host/register-task.ps1
#
# Сам демон — host/vm-relay.py (он же поднимает три ssh-процесса и следит за ними).

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = (Get-Command pythonw.exe -ErrorAction SilentlyContinue)
if (-not $python) { $python = (Get-Command python.exe) }

$action = New-ScheduledTaskAction `
    -Execute $python.Source `
    -Argument "`"$here\vm-relay.py`" daemon" `
    -WorkingDirectory $here

$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERNAME"

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan)

Register-ScheduledTask -TaskName 'vm-relay' -Action $action -Trigger $trigger `
    -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName 'vm-relay'

Write-Output "vm-relay зарегистрирован и запущен; проверка: python vm-relay.py status"
