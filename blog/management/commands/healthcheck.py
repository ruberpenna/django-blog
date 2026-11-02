import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime

from django.conf import settings
from django.core.management.base import BaseCommand

from blog.notify import send_telegram

# 확인할 곳: (이름, 주소, 이 단계를 담당하는 서비스)
CHECKS = [
    ('Django(Waitress)', 'http://127.0.0.1:8000/', 'blog-waitress'),
    ('Caddy', 'http://127.0.0.1:8123/', 'blog-caddy'),
    ('외부 주소(NPM)', 'https://django.pennatic.info/', None),
]
REPEAT_ALERT_SECONDS = 60 * 60  # 장애가 계속되면 1시간마다 다시 알림
STATE_FILE = os.path.join(settings.BASE_DIR, 'logs', 'healthcheck_state.json')


def check(url):
    """200 이면 None, 아니면 실패 사유"""
    req = urllib.request.Request(url, headers={'User-Agent': 'blog-healthcheck'})
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            return None if res.status == 200 else f'HTTP {res.status}'
    except urllib.error.HTTPError as e:
        return f'HTTP {e.code}'
    except Exception as e:  # 연결 거부, 시간 초과 등
        return type(e).__name__ + (f': {e.reason}' if hasattr(e, 'reason') else '')


def service_state(name):
    out = subprocess.run(['sc.exe', 'query', name], capture_output=True, text=True, errors='replace').stdout
    for state in ('RUNNING', 'STOPPED', 'START_PENDING', 'STOP_PENDING'):
        if state in out:
            return state
    return 'UNKNOWN'


def boot_time():
    out = subprocess.run(['powershell', '-NoProfile', '-Command',
                          '(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToString("o")'],
                         capture_output=True, text=True, errors='replace').stdout.strip()
    return out or None


class Command(BaseCommand):
    help = '블로그 상태 확인: 문제가 있으면 멈춘 서비스를 다시 켜고 텔레그램으로 알림 (작업 스케줄러가 5분마다 실행)'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='확인만 하고 서비스 재시작/알림/상태 저장 안 함')

    def handle(self, *args, **options):
        dry = options['dry_run']
        state = self.load_state()
        now = time.time()
        messages = []

        # 재부팅 감지
        boot = boot_time()
        if boot and state.get('boot') and boot != state['boot']:
            messages.append(f'🔄 서버 PC가 재부팅됐습니다 ({boot[:16].replace("T", " ")})')
        if boot:
            state['boot'] = boot

        failures = [(name, url, svc, err) for name, url, svc in CHECKS if (err := check(url))]

        # 멈춘 서비스는 다시 켜고 한 번 더 확인
        restarted = []
        if failures and not dry:
            for name, url, svc, err in failures:
                if svc and service_state(svc) != 'RUNNING':
                    subprocess.run(['sc.exe', 'start', svc], capture_output=True)
                    restarted.append(svc)
            if restarted:
                time.sleep(15)
                failures = [(name, url, svc, err) for name, url, svc in CHECKS if (err := check(url))]

        detail = '\n'.join(f'- {name}: {err}' for name, _, _, err in failures)
        if restarted:
            detail += f'\n(자동으로 다시 켠 서비스: {", ".join(restarted)})'

        if failures:
            first = not state.get('down_since')
            if first:
                state['down_since'] = now
            if first or now - state.get('last_alert', 0) >= REPEAT_ALERT_SECONDS:
                minutes = int((now - state['down_since']) // 60)
                head = '🚨 블로그 접속 장애' if first else f'🚨 블로그 장애 계속 ({minutes}분째)'
                messages.append(f'{head}\n{detail}\n\nhttps://django.pennatic.info/')
                state['last_alert'] = now
        else:
            note = f'\n(자동으로 다시 켠 서비스: {", ".join(restarted)})' if restarted else ''
            if state.get('down_since'):
                minutes = int((now - state['down_since']) // 60)
                messages.append(f'✅ 블로그 복구됨 (장애 약 {minutes}분){note}')
            elif restarted:
                messages.append(f'🔧 멈춰 있던 서비스를 자동으로 다시 켰습니다. 지금은 정상입니다.{note}')
            state.pop('down_since', None)
            state.pop('last_alert', None)

        stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.stdout.write(f'{stamp} ' + ('정상' if not failures else '장애\n' + detail))
        if dry:
            for m in messages:
                self.stdout.write('[알림 예정] ' + m)
            return
        for m in messages:
            send_telegram(m)
        self.save_state(state)

    def load_state(self):
        try:
            with open(STATE_FILE, encoding='utf-8') as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def save_state(self, state):
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f)
