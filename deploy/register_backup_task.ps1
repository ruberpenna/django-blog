# 매일 새벽 4시에 backup_db.ps1 을 실행하는 작업 스케줄러 등록 (관리자 PowerShell에서 실행)
# 로그인하지 않아도 실행되도록 SYSTEM 계정으로 등록합니다.
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'backup_db.ps1'

$action = New-ScheduledTaskAction -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
$trigger = New-ScheduledTaskTrigger -Daily -At 4:00
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName 'blog-db-backup' -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null

# 등록 확인 (Get-ScheduledTask 는 다른 손상된 작업이 있으면 실패할 수 있어 schtasks 사용)
schtasks /query /tn blog-db-backup /fo LIST
