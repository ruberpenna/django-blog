# 운영 서버 설치 안내 (Windows)

블로그를 상시 실행할 PC에서 진행합니다. 구성은 아래와 같습니다.

```
인터넷 → 공유기(80/443) → Nginx Proxy Manager(HTTPS, 다른 PC) → Caddy(이 PC :8123, /static, /media) → Waitress(127.0.0.1:8000, Django) → PostgreSQL(DB 서버 PC, 내부망)
```

HTTPS 인증서는 NPM이 발급·관리합니다. NPM의 Proxy Host에서 블로그 도메인을 `http://<이 PC 내부 IP>:8123`으로 전달하도록 설정합니다.

아래 예시의 값은 실제 값으로 바꿔서 입력하세요.

| 예시 | 의미 |
|---|---|
| `E:\django_blog` | 이 PC의 프로젝트 폴더 |
| `myblog.duckdns.org` | 블로그 도메인 |
| `192.168.0.10` | DB 서버 PC의 내부 IP |

명령은 모두 **관리자 권한 PowerShell**에서, 별도 표시가 없으면 프로젝트 폴더에서 실행합니다.

---

## 1. 코드와 패키지

Python 3.10 이상이 필요합니다 (Django 5.2). 3.12 기준으로 설명합니다.

```powershell
winget install --id Python.Python.3.12 --exact
cd E:\django_blog
git pull
py -3.12 -m venv myvenv
myvenv\Scripts\python.exe -m pip install -r requirements.txt
```

## 2. `.env` 운영 설정

`.env`에 아래 항목을 추가하거나 수정합니다.

```
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=myblog.duckdns.org,localhost,127.0.0.1
DJANGO_HTTPS=True
DB_HOST=192.168.0.10
```

## 3. 정적 파일 수집, 동작 확인

```powershell
myvenv\Scripts\python.exe manage.py collectstatic --noinput
deploy\run_waitress.bat
```

브라우저에서 `http://localhost:8000`을 열어 글 목록이 나오면 정상입니다. 이 단계에서는 CSS가 빠져 보이는 게 정상이고, Caddy를 붙이면 해결됩니다. 확인한 뒤 `Ctrl+C`로 종료합니다.

## 4. 도메인 (DuckDNS, 무료)

1. https://www.duckdns.org 에 로그인하고 서브도메인(예: `myblog`)을 만듭니다.
2. current ip가 집 공인 IP와 같은지 확인합니다.
3. 집 공인 IP가 바뀔 수 있으면 DuckDNS 사이트의 "install" → Windows 안내에 따라 IP 자동 갱신을 설정합니다.

## 5. 네트워크

1. **이 PC 내부 IP 고정**: 공유기 관리 페이지의 DHCP 고정 할당(예약)에 이 PC를 등록합니다.
2. **NPM 설정**: 공유기의 80/443은 NPM이 있는 PC로 포트포워딩되어 있어야 합니다. NPM에서 Proxy Host를 추가합니다.
   - Domain: 블로그 도메인 / Scheme: `http` / Forward IP: 이 PC 내부 IP / Port: `8123`
   - SSL 탭에서 Let's Encrypt 인증서 발급, Force SSL 켜기
3. **Windows 방화벽 허용** (내부망에서 오는 8123만 허용)
   ```powershell
   New-NetFirewallRule -DisplayName "Blog 8123" -Direction Inbound -Protocol TCP -LocalPort 8123 -RemoteAddress LocalSubnet -Action Allow
   ```
4. **절전 끄기** (전원 연결 시 절전·최대 절전 안 함)
   ```powershell
   powercfg /change standby-timeout-ac 0
   powercfg /change hibernate-timeout-ac 0
   ```

## 6. Caddy, NSSM 설치

```powershell
winget install --id CaddyServer.Caddy --exact
winget install --id NSSM.NSSM --exact
```

설치한 뒤 **PowerShell을 새로 열고** 경로를 확인합니다.

```powershell
(Get-Command caddy).Source
(Get-Command nssm).Source
```

서비스는 시스템 계정으로 실행되기 때문에, 사용자 폴더 아래에 설치된 caddy.exe는 `C:\caddy`로 복사해서 씁니다.

```powershell
New-Item -ItemType Directory -Force C:\caddy
Copy-Item (Get-Command caddy).Source C:\caddy\caddy.exe
```

## 7. 서비스 등록 (재부팅해도 자동 실행)

```powershell
New-Item -ItemType Directory -Force E:\django_blog\logs

# Django (Waitress)
nssm install blog-waitress "E:\django_blog\myvenv\Scripts\waitress-serve.exe" "--listen=127.0.0.1:8000 --threads=8 --trusted-proxy=127.0.0.1 --trusted-proxy-headers=x-forwarded-proto mysite.wsgi:application"
nssm set blog-waitress AppDirectory "E:\django_blog"
nssm set blog-waitress AppStdout "E:\django_blog\logs\waitress.log"
nssm set blog-waitress AppStderr "E:\django_blog\logs\waitress.log"
nssm set blog-waitress Start SERVICE_AUTO_START
nssm start blog-waitress

# Caddy
nssm install blog-caddy "C:\caddy\caddy.exe" "run --config E:\django_blog\deploy\Caddyfile"
nssm set blog-caddy AppDirectory "C:\caddy"
nssm set blog-caddy AppEnvironmentExtra BLOG_ROOT=E:/django_blog
nssm set blog-caddy AppStdout "E:\django_blog\logs\caddy.log"
nssm set blog-caddy AppStderr "E:\django_blog\logs\caddy.log"
nssm set blog-caddy Start SERVICE_AUTO_START
nssm start blog-caddy
```

`BLOG_ROOT`는 역슬래시(`\`) 대신 슬래시(`/`)로 적습니다.

상태 확인:

```powershell
nssm status blog-waitress
nssm status blog-caddy
```

Caddy는 HTTPS 없이 `:8123`에서 HTTP만 받습니다(인증서는 NPM 담당). 문제가 생기면 `logs\caddy.log`, `logs\waitress.log`를 확인하세요.

## 8. 확인

- 휴대폰 데이터망(와이파이 끔)에서 `https://myblog.duckdns.org` 접속
- 로그인, 글쓰기, 이미지 업로드 확인
- PC를 재부팅한 뒤 자동으로 다시 열리는지 확인

## 9. DB 서버 보안 (DB 서버 PC에서)

블로그가 내부망으로 DB에 접속하므로, DB 포트를 외부에 열어둘 필요가 없습니다.

1. **공유기에서 5432 포트포워딩을 삭제**합니다.
2. `pg_hba.conf`(PostgreSQL 데이터 폴더)에서 내부망만 허용합니다. 대역은 실제 내부망에 맞게 바꾸세요.
   ```
   host    all    all    192.168.0.0/24    scram-sha-256
   ```
   기존에 `0.0.0.0/0`처럼 전체를 허용하는 줄이 있으면 지웁니다. 인증 방식(`scram-sha-256` 또는 `md5`)은 기존 줄과 같게 맞추세요.
3. PostgreSQL 서비스를 재시작합니다.

주의: 외부에서 이 DB로 직접 개발하던 PC가 있다면, 이후로는 접속이 안 됩니다. 그 PC는 같은 내부망에서 작업하거나 VPN을 사용해야 합니다.

---

## 코드 업데이트 반영

개발 PC에서 push한 다음, 이 PC의 관리자 권한 명령 프롬프트에서 실행합니다.

```
E:\django_blog\deploy\update.bat
```

`git pull` → 패키지 설치 → 정적 파일 수집 → DB 마이그레이션 → 서비스 재시작 순서로 진행합니다.

## DB 자동 백업

`deploy\backup_db.ps1`이 DB를 `pg_dump`로 덤프하고 업로드 파일(`media`)을 복사합니다. 기본 저장 위치는 `G:\blog_backups`이고, 30일 지난 DB 덤프는 지웁니다(최소 7개는 유지).

1. PostgreSQL 명령줄 도구 설치 (DB 서버와 같은 15 버전, 서버는 설치하지 않음)
   ```powershell
   winget install --id PostgreSQL.PostgreSQL.15 --exact --override "--mode unattended --unattendedmodeui none --disable-components server,pgAdmin,stackbuilder"
   ```
2. 수동으로 한 번 실행해서 확인
   ```powershell
   powershell -ExecutionPolicy Bypass -File deploy\backup_db.ps1
   ```
3. 매일 새벽 4시 자동 실행 등록 (SYSTEM 계정, 로그인 불필요)
   ```powershell
   powershell -ExecutionPolicy Bypass -File deploy\register_backup_task.ps1
   ```

저장 위치를 바꾸려면 `backup_db.ps1` 맨 위의 `$BackupDir`를 수정합니다. 결과는 `logs\backup.log`에 남습니다.

복원 (주의: DB 내용을 백업 시점으로 덮어씀):

```powershell
$env:PGPASSWORD = "<DB 비밀번호>"
& "C:\Program Files\PostgreSQL\15\bin\pg_restore.exe" --host 192.168.0.10 --username postgres --dbname postgres --clean --if-exists --no-owner G:\blog_backups\db\<파일명>.dump
```

## 서비스 관리

```powershell
nssm restart blog-waitress   # Django 재시작
nssm stop blog-caddy         # Caddy 중지
nssm edit blog-waitress      # 설정 화면 열기
nssm remove blog-waitress confirm   # 서비스 삭제
```
