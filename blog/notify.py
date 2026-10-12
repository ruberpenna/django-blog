import json
import logging
import threading
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger('django')

API_URL = 'https://api.telegram.org/bot{token}/{method}'


def telegram_api(method, params=None, timeout=10):
    """텔레그램 Bot API 호출. 응답 JSON 반환"""
    url = API_URL.format(token=settings.TELEGRAM_BOT_TOKEN, method=method)
    data = urllib.parse.urlencode(params).encode() if params else None
    with urllib.request.urlopen(url, data=data, timeout=timeout) as res:
        return json.loads(res.read().decode())


def send_telegram(text):
    """텔레그램으로 메시지 전송. 실패해도 예외를 밖으로 던지지 않음"""
    if not (settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID):
        return False
    try:
        telegram_api('sendMessage', {
            'chat_id': settings.TELEGRAM_CHAT_ID,
            'text': text,
            'disable_web_page_preview': 'true',
        })
        return True
    except Exception as e:
        logger.warning('텔레그램 알림 전송 실패: %s', e)
        return False


def notify_new_comment(request, comment):
    """새 댓글 알림 (응답이 늦어지지 않게 백그라운드 전송)"""
    post = comment.post
    text = (
        f'💬 새 댓글 (승인 대기)\n'
        f'글: {post.title}\n'
        f'작성자: {comment.author}\n\n'
        f'{comment.text[:300]}\n\n'
        f'{request.build_absolute_uri(post.get_absolute_url())}'
    )
    threading.Thread(target=send_telegram, args=(text,), daemon=True).start()
