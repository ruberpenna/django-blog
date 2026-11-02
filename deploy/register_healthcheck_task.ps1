# 5분마다 블로그 상태를 확인하는 작업 스케줄러 등록 (관리자 PowerShell 에서 실행)
#   manage.py healthcheck: 응답이 없으면 멈춘 서비스를 다시 켜고 텔레그램으로 알림
# SYSTEM 계정으로 등록해서 로그인하지 않아도, 재부팅 직후에도 실행됩니다.
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root 'myvenv\Scripts\python.exe'
$log = Join-Path $root 'logs\healthcheck.log'

$action = New-ScheduledTaskAction -Execute 'cmd.exe' -WorkingDirectory $root `
    -Argument "/c `"`"$python`" manage.py healthcheck >> `"$log`" 2>&1`""
$every5min = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
$atBoot = New-ScheduledTaskTrigger -AtStartup
$atBoot.Delay = 'PT3M'  # 부팅 직후 외장 드라이브가 준비될 시간
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 4)
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName 'blog-healthcheck' -Action $action -Trigger @($every5min, $atBoot) `
    -Settings $settings -Principal $principal -Force | Out-Null

# 등록 확인 (Get-ScheduledTask 는 다른 손상된 작업이 있으면 실패할 수 있어 schtasks 사용)
schtasks /query /tn blog-healthcheck /fo LIST
