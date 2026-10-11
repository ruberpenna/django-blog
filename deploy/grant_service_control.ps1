# 현재 사용자에게 블로그 서비스(blog-waitress, blog-caddy)의 시작/중지 권한 부여
# 관리자 PowerShell에서 한 번만 실행. 이후 관리자 창 없이 재시작 가능
#   nssm restart blog-waitress   /   deploy\update.bat
# 부여하는 권한: 시작(RP), 중지(WP), 일시정지(DT), 상태 조회(LC, LO, CC, SW), 제어(CR), 읽기(RC)
# 서비스 설정 변경/삭제 권한은 주지 않음
param([string]$User = "$env:USERDOMAIN\$env:USERNAME")
$ErrorActionPreference = 'Stop'

$sid = (New-Object System.Security.Principal.NTAccount $User).Translate([System.Security.Principal.SecurityIdentifier]).Value
$ace = "(A;;CCLCSWRPWPDTLOCRRC;;;$sid)"

foreach ($svc in 'blog-waitress', 'blog-caddy') {
    $sd = (sc.exe sdshow $svc | Where-Object { $_ -match '^D:' }) -join ''
    if (-not $sd) { throw "$svc 서비스의 보안 설정을 읽지 못했습니다." }
    if ($sd -like "*;;;$sid)*") { Write-Output "$svc : 이미 권한 있음"; continue }

    # DACL(D:...) 끝, SACL(S:...) 앞에 ACE 추가
    if ($sd -match '^(D:.*?)(S:.*)?$') { $newSd = $Matches[1] + $ace + $Matches[2] }
    sc.exe sdset $svc $newSd | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "$svc 권한 설정 실패 (exit $LASTEXITCODE)" }
    Write-Output "$svc : $User 에게 시작/중지 권한 부여"
}
