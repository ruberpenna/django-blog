@echo off
rem 운영 서버 수동 실행 (테스트용). 서비스 등록은 deploy\README.md 참고
cd /d "%~dp0.."
myvenv\Scripts\waitress-serve.exe --listen=127.0.0.1:8123 --threads=8 --trusted-proxy=127.0.0.1 --trusted-proxy-headers=x-forwarded-proto mysite.wsgi:application
