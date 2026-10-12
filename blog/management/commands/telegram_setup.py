from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from blog.notify import send_telegram, telegram_api


class Command(BaseCommand):
    help = '텔레그램 알림 설정 도우미: 채팅 ID 확인(기본), --test 로 테스트 메시지 전송'

    def add_arguments(self, parser):
        parser.add_argument('--test', action='store_true', help='테스트 메시지 전송')

    def handle(self, *args, **options):
        if not settings.TELEGRAM_BOT_TOKEN:
            raise CommandError('.env 에 TELEGRAM_BOT_TOKEN 을 먼저 넣으세요.')

        if options['test']:
            if not settings.TELEGRAM_CHAT_ID:
                raise CommandError('.env 에 TELEGRAM_CHAT_ID 를 먼저 넣으세요.')
            if send_telegram('✅ Pennatic Blog 알림 테스트'):
                self.stdout.write(self.style.SUCCESS('전송 성공. 텔레그램을 확인하세요.'))
            else:
                raise CommandError('전송 실패. 토큰/채팅 ID 와 logs 를 확인하세요.')
            return

        # 봇에게 보낸 최근 메시지에서 채팅 ID 찾기
        result = telegram_api('getUpdates').get('result', [])
        chats = {}
        for update in result:
            chat = (update.get('message') or {}).get('chat')
            if chat:
                chats[chat['id']] = chat.get('username') or chat.get('first_name') or chat.get('title', '')
        if not chats:
            self.stdout.write('채팅을 찾지 못했습니다. 텔레그램에서 봇에게 아무 메시지나 보낸 뒤 다시 실행하세요.')
            return
        for chat_id, name in chats.items():
            self.stdout.write(f'TELEGRAM_CHAT_ID={chat_id}   ({name})')
