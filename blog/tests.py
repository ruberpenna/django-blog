from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from django.core import signing
from django.core.cache import cache

from .models import Post


def comment_data(author='방문자', text='좋은 글이네요', seconds_ago=10, **extra):
    """정상 사용자가 폼을 열고 seconds_ago 초 뒤 제출한 댓글 데이터"""
    import time
    data = {'author': author, 'text': text, 'website': '',
            'ts': signing.dumps(time.time() - seconds_ago, salt='comment-form')}
    data.update(extra)
    return data


# 승인 대기 글은 로그인한 사용자만 볼 수 있음
class DraftVisibilityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('tester', password='test-pass-123')
        self.published = Post.objects.create(
            author=self.user, title='발행 글', text='<p>본문</p>', ctg='기타',
            published_date=timezone.now() - timedelta(days=1))
        self.draft = Post.objects.create(
            author=self.user, title='대기 글', text='<p>본문</p>', ctg='기타')

    def test_anonymous_sees_published(self):
        res = self.client.get(reverse('post_detail', kwargs={'pk': self.published.pk}))
        self.assertEqual(res.status_code, 200)

    def test_anonymous_cannot_see_draft(self):
        res = self.client.get(reverse('post_detail', kwargs={'pk': self.draft.pk}))
        self.assertEqual(res.status_code, 404)

    def test_anonymous_cannot_comment_on_draft(self):
        res = self.client.get(reverse('add_comment_to_post', kwargs={'pk': self.draft.pk}))
        self.assertEqual(res.status_code, 404)
        res = self.client.post(reverse('add_comment_to_post', kwargs={'pk': self.draft.pk}),
                               comment_data('spam', 'spam'))
        self.assertEqual(res.status_code, 404)
        self.assertEqual(self.draft.comments.count(), 0)

    def test_logged_in_sees_draft(self):
        self.client.force_login(self.user)
        res = self.client.get(reverse('post_detail', kwargs={'pk': self.draft.pk}))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, '<meta name="robots" content="noindex">')

    def test_draft_not_in_sitemap(self):
        res = self.client.get('/sitemap.xml')
        self.assertContains(res, reverse('post_detail', kwargs={'pk': self.published.pk}))
        self.assertNotContains(res, reverse('post_detail', kwargs={'pk': self.draft.pk}))


# 새 댓글 텔레그램 알림
class CommentNotifyTests(TestCase):
    def setUp(self):
        cache.clear()
        user = User.objects.create_user('tester', password='test-pass-123')
        self.post = Post.objects.create(
            author=user, title='알림 글', text='<p>본문</p>', ctg='기타',
            published_date=timezone.now() - timedelta(days=1))

    def add_comment(self):
        # 백그라운드 스레드 대신 바로 실행해서 결과 확인
        with mock.patch('blog.notify.threading.Thread') as thread:
            thread.side_effect = lambda target, args, daemon: mock.Mock(start=lambda: target(*args))
            return self.client.post(reverse('add_comment_to_post', kwargs={'pk': self.post.pk}),
                                    comment_data())

    @override_settings(TELEGRAM_BOT_TOKEN='123:abc', TELEGRAM_CHAT_ID='42')
    def test_sends_message_on_new_comment(self):
        with mock.patch('blog.notify.telegram_api') as api:
            res = self.add_comment()
        self.assertEqual(res.status_code, 302)
        api.assert_called_once()
        method, params = api.call_args[0]
        self.assertEqual(method, 'sendMessage')
        self.assertEqual(params['chat_id'], '42')
        self.assertIn('알림 글', params['text'])
        self.assertIn('방문자', params['text'])
        self.assertIn(f'/post/{self.post.pk}/', params['text'])

    @override_settings(TELEGRAM_BOT_TOKEN='', TELEGRAM_CHAT_ID='')
    def test_disabled_without_settings(self):
        with mock.patch('blog.notify.telegram_api') as api:
            res = self.add_comment()
        self.assertEqual(res.status_code, 302)
        api.assert_not_called()

    @override_settings(TELEGRAM_BOT_TOKEN='123:abc', TELEGRAM_CHAT_ID='42')
    def test_comment_saved_even_if_telegram_fails(self):
        with mock.patch('blog.notify.telegram_api', side_effect=OSError('network down')):
            res = self.add_comment()
        self.assertEqual(res.status_code, 302)
        self.assertEqual(self.post.comments.count(), 1)


# 댓글 스팸 방지
@override_settings(TELEGRAM_BOT_TOKEN='', TELEGRAM_CHAT_ID='')
class CommentSpamTests(TestCase):
    def setUp(self):
        cache.clear()
        user = User.objects.create_user('tester', password='test-pass-123')
        self.post = Post.objects.create(
            author=user, title='스팸 테스트 글', text='<p>본문</p>', ctg='기타',
            published_date=timezone.now() - timedelta(days=1))
        self.url = reverse('add_comment_to_post', kwargs={'pk': self.post.pk})

    def post_comment(self, data, ip='8.8.4.4'):
        # 운영 구조(NPM -> Caddy)처럼 X-Forwarded-For 마지막에 내부 프록시 주소가 붙음
        return self.client.post(self.url, data, HTTP_X_FORWARDED_FOR=f'{ip}, 192.168.0.5')

    def test_form_has_hidden_fields(self):
        res = self.client.get(self.url)
        self.assertContains(res, 'name="website"')
        self.assertContains(res, 'name="ts"')

    def test_normal_comment_saved(self):
        res = self.post_comment(comment_data())
        self.assertEqual(res.status_code, 302)
        self.assertEqual(self.post.comments.count(), 1)

    def test_honeypot_silently_dropped(self):
        res = self.post_comment(comment_data(website='http://spam.example'))
        self.assertEqual(res.status_code, 302)  # 봇에게는 성공처럼 보임
        self.assertEqual(self.post.comments.count(), 0)

    def test_too_fast_rejected(self):
        res = self.post_comment(comment_data(seconds_ago=1))
        self.assertContains(res, '너무 빨리')
        self.assertEqual(self.post.comments.count(), 0)

    def test_missing_or_forged_timestamp_rejected(self):
        self.assertContains(self.post_comment(comment_data(ts='')), '새로고침')
        self.assertContains(self.post_comment(comment_data(ts='123:forged')), '새로고침')
        self.assertEqual(self.post.comments.count(), 0)

    def test_too_many_links_rejected(self):
        text = 'http://a.example http://b.example www.c.example'
        res = self.post_comment(comment_data(text=text))
        self.assertContains(res, '링크는 2개까지')
        self.assertEqual(self.post.comments.count(), 0)
        self.assertEqual(self.post_comment(comment_data(text='http://a.example 참고')).status_code, 302)

    def test_rate_limit_per_ip(self):
        for i in range(3):
            self.assertEqual(self.post_comment(comment_data(text=f'댓글 {i}')).status_code, 302)
        res = self.post_comment(comment_data(text='네 번째'))
        self.assertEqual(res.status_code, 429)
        self.assertContains(res, '10분 뒤', status_code=429)
        # 다른 IP 는 영향 없음
        self.assertEqual(self.post_comment(comment_data(), ip='1.0.0.1').status_code, 302)
        self.assertEqual(self.post.comments.count(), 4)

    def test_spoofed_forwarded_for_does_not_bypass_limit(self):
        # 방문자가 X-Forwarded-For 앞쪽에 가짜 IP 를 넣어도 실제 IP(오른쪽)로 집계
        for i in range(3):
            self.post_comment(comment_data(text=f'댓글 {i}'), ip=f'5.5.5.{i}, 8.8.4.4')
        res = self.post_comment(comment_data(), ip='1.2.3.4, 8.8.4.4')
        self.assertEqual(res.status_code, 429)

    def test_real_ip_header_preferred(self):
        # 운영에서는 Caddy 가 X-Real-IP 로 실제 IP 를 전달 (Waitress 가 X-Forwarded-For 를 지움)
        for i in range(3):
            self.client.post(self.url, comment_data(text=f'댓글 {i}'), HTTP_X_REAL_IP='8.8.8.8')
        res = self.client.post(self.url, comment_data(), HTTP_X_REAL_IP='8.8.8.8')
        self.assertEqual(res.status_code, 429)
        res = self.client.post(self.url, comment_data(), HTTP_X_REAL_IP='1.1.1.1')
        self.assertEqual(res.status_code, 302)
