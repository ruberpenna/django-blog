from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
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
