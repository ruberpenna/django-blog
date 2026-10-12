from datetime import timedelta
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Post


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
                               {'author': 'spam', 'text': 'spam'})
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
        user = User.objects.create_user('tester', password='test-pass-123')
        self.post = Post.objects.create(
            author=user, title='알림 글', text='<p>본문</p>', ctg='기타',
            published_date=timezone.now() - timedelta(days=1))

    def add_comment(self):
        # 백그라운드 스레드 대신 바로 실행해서 결과 확인
        with mock.patch('blog.notify.threading.Thread') as thread:
            thread.side_effect = lambda target, args, daemon: mock.Mock(start=lambda: target(*args))
            return self.client.post(reverse('add_comment_to_post', kwargs={'pk': self.post.pk}),
                                    {'author': '방문자', 'text': '좋은 글이네요'})

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
