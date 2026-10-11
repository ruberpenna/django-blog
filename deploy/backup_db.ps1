# 블로그 백업: PostgreSQL DB 덤프 + 업로드 파일(media) 복사
# 작업 스케줄러가 매일 실행 (deploy\README.md "DB 자동 백업" 참고)
#   수동 실행: powershell -ExecutionPolicy Bypass -File deploy\backup_db.ps1
param(
    [string]$BackupDir = 'G:\blog_backups',  # 백업 저장 위치
    [int]$KeepDays = 30                      # 이 기간보다 오래된 DB 덤프는 삭제
)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$pgDump = 'C:\Program Files\PostgreSQL\15\bin\pg_dump.exe'
$logFile = Join-Path $root 'logs\backup.log'

function Write-Log([string]$msg) {
    $line = '{0} {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Add-Content -Path $logFile -Value $line -Encoding UTF8
    Write-Output $line
}

# .env 에서 DB 접속 정보 읽기
function Read-Env([string]$path) {
    $vars = @{}
    foreach ($line in [IO.File]::ReadAllLines($path)) {
        if ($line -match '^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.*)$') {
            $vars[$Matches[1]] = $Matches[2].Trim().Trim("'").Trim('"')
        }
    }
    return $vars
}

New-Item -ItemType Directory -Force (Join-Path $root 'logs') | Out-Null
$dbDir = Join-Path $BackupDir 'db'
$mediaDir = Join-Path $BackupDir 'media'
New-Item -ItemType Directory -Force $dbDir, $mediaDir | Out-Null

try {
    $envVars = Read-Env (Join-Path $root '.env')
    $dbName = $envVars['DB_NAME']
    $dumpFile = Join-Path $dbDir ('{0}_{1}.dump' -f $dbName, (Get-Date -Format 'yyyyMMdd_HHmmss'))

    # 1. DB 덤프 (custom 형식: pg_restore 로 복원)
    $env:PGPASSWORD = $envVars['DB_PASSWORD']
    & $pgDump --host $envVars['DB_HOST'] --port $envVars['DB_PORT'] --username $envVars['DB_USER'] `
        --format custom --no-owner --file $dumpFile $dbName
    if ($LASTEXITCODE -ne 0) { throw "pg_dump 실패 (exit $LASTEXITCODE)" }
    $size = [math]::Round((Get-Item $dumpFile).Length / 1KB)
    Write-Log "DB 백업 완료: $dumpFile (${size}KB)"

    # 2. 업로드 파일 복사 (변경분만, 원본에서 지워진 파일도 백업에는 유지)
    robocopy (Join-Path $root 'media') $mediaDir /E /XO /R:2 /W:5 /NP /NFL /NDL /NJH /NJS | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "media 복사 실패 (robocopy exit $LASTEXITCODE)" }
    Write-Log "media 복사 완료: $mediaDir"

    # 3. 오래된 DB 덤프 정리 (최소 7개는 남김)
    $old = Get-ChildItem $dbDir -Filter '*.dump' | Sort-Object LastWriteTime -Descending |
        Select-Object -Skip 7 | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$KeepDays) }
    foreach ($f in $old) { Remove-Item $f.FullName -Force; Write-Log "오래된 백업 삭제: $($f.Name)" }
}
catch {
    Write-Log "백업 실패: $($_.Exception.Message)"
    exit 1
}
finally {
    Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue
}
