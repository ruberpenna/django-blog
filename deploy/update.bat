@echo off
chcp 65001 >nul
rem 운영 서버 업데이트: 최신 코드 받기 -> 패키지 설치 -> 정적 파일 수집 -> 서비스 재시작
rem 관리자 권한 명령 프롬프트에서 실행하세요
cd /d "%~dp0.."
git pull || goto :error
myvenv\Scripts\python.exe -m pip install -r requirements.txt || goto :error
myvenv\Scripts\python.exe manage.py collectstatic --noinput || goto :error
myvenv\Scripts\python.exe manage.py migrate || goto :error
nssm restart blog-waitress || goto :error
echo.
echo 업데이트 완료
exit /b 0

:error
echo.
echo 업데이트 중 오류가 발생했습니다. 위 메시지를 확인하세요.
exit /b 1
