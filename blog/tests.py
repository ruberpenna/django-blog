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
    data = {'author': author, 'text': text, 'leave_blank': '',
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
        self.assertContains(res, 'name="leave_blank"')
        self.assertNotContains(res, 'name="website"')
        self.assertContains(res, 'name="ts"')

    def test_normal_comment_saved(self):
        res = self.post_comment(comment_data())
        self.assertEqual(res.status_code, 302)
        self.assertEqual(self.post.comments.count(), 1)

    def test_honeypot_silently_dropped(self):
        res = self.post_comment(comment_data(leave_blank='http://spam.example'))
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

    def test_www_link_counted_once(self):
        # https://www. 형태도 링크 1개로 셈 (2개까지 허용)
        text = 'https://www.a.example 와 https://www.b.example 참고'
        self.assertEqual(self.post_comment(comment_data(text=text)).status_code, 302)
        text += ' www.c.example'
        self.assertContains(self.post_comment(comment_data(text=text)), '링크는 2개까지')

    def test_error_rerender_gets_fresh_timestamp(self):
        # 만료/위조 ts 로 실패해도 다시 그린 폼에는 새 ts 가 들어가서, 그대로 재제출하면 성공
        import re as _re, time as _time
        past = _time.time() - 60 * 60 * 25
        with mock.patch('django.core.signing.time.time', return_value=past):  # 25시간 전에 연 폼
            expired = signing.dumps(past, salt='comment-form')
        res = self.post_comment(comment_data(ts=expired))
        self.assertContains(res, '새로고침')
        new_ts = _re.search(r'name="ts" value="([^"]+)"', res.content.decode()).group(1)
        self.assertNotEqual(new_ts, expired)
        # 사람이 다시 누르기까지 걸리는 시간만큼 지난 것처럼 처리
        with mock.patch('blog.forms.time.time', return_value=_time.time() + 5):
            res = self.post_comment(comment_data(ts=new_ts))
        self.assertEqual(res.status_code, 302)
        self.assertEqual(self.post.comments.count(), 1)

    def test_rate_limit_counts_atomically(self):
        # 판정은 incr 결과로: 4번째부터 차단되고 횟수는 계속 증가
        for i in range(3):
            self.assertEqual(self.post_comment(comment_data(text=f'댓글 {i}')).status_code, 302)
        for _ in range(2):
            self.assertEqual(self.post_comment(comment_data()).status_code, 429)
        self.assertEqual(cache.get('comment-rate:8.8.4.4'), 5)


# 조회수
class ViewCountTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('tester', password='test-pass-123')
        self.post = Post.objects.create(
            author=self.user, title='조회수 글', text='<p>본문</p>', ctg='기타',
            published_date=timezone.now() - timedelta(days=1))
        self.url = reverse('post_detail', kwargs={'pk': self.post.pk})

    def views(self):
        self.post.refresh_from_db()
        return self.post.view_count

    def test_counts_and_shows(self):
        res = self.client.get(self.url, HTTP_X_REAL_IP='8.8.8.8')
        self.assertEqual(self.views(), 1)
        self.assertContains(res, 'glyphicon-eye-open"></span> 1')

    def test_same_ip_counted_once_per_window(self):
        for _ in range(3):
            self.client.get(self.url, HTTP_X_REAL_IP='8.8.8.8')
        self.assertEqual(self.views(), 1)
        self.client.get(self.url, HTTP_X_REAL_IP='1.1.1.1')
        self.assertEqual(self.views(), 2)

    def test_logged_in_and_bots_not_counted(self):
        self.client.get(self.url, HTTP_USER_AGENT='Mozilla/5.0 (compatible; Googlebot/2.1)', HTTP_X_REAL_IP='8.8.8.8')
        self.client.get(self.url, HTTP_USER_AGENT='facebookexternalhit/1.1', HTTP_X_REAL_IP='1.1.1.1')
        self.client.force_login(self.user)
        self.client.get(self.url, HTTP_X_REAL_IP='9.9.9.9')
        self.assertEqual(self.views(), 0)

    def test_draft_not_counted(self):
        draft = Post.objects.create(author=self.user, title='대기', text='x', ctg='기타')
        self.client.get(reverse('post_detail', kwargs={'pk': draft.pk}))  # 비로그인 404
        draft.refresh_from_db()
        self.assertEqual(draft.view_count, 0)

    def test_popular_sidebar(self):
        other = Post.objects.create(author=self.user, title='덜 본 글', text='x', ctg='기타',
                                    published_date=timezone.now() - timedelta(days=2), view_count=1)
        Post.objects.filter(pk=self.post.pk).update(view_count=5)
        res = self.client.get('/', HTTP_USER_AGENT='Googlebot')
        popular = list(res.context['sidebar_popular'])
        self.assertEqual(popular, [self.post, other])
        self.assertContains(res, '인기 글')


# 비공개 글
class PrivatePostTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user('tester', password='test-pass-123')
        past = timezone.now() - timedelta(days=1)
        self.public = Post.objects.create(author=self.user, title='공개 글', text='<p>공개 본문</p>',
                                          ctg='기타', published_date=past)
        self.private = Post.objects.create(author=self.user, title='비밀 글', text='<p>비밀 본문</p>',
                                           ctg='비밀카테고리', published_date=past, is_private=True)
        self.detail = reverse('post_detail', kwargs={'pk': self.private.pk})
        self.toggle = reverse('post_toggle_private', kwargs={'pk': self.public.pk})

    def test_hidden_everywhere_for_anonymous(self):
        for url in ['/', '/srch/?kwd=비밀', '/srch/?ctg=비밀카테고리', '/sitemap.xml']:
            res = self.client.get(url)
            self.assertNotContains(res, '비밀 글', msg_prefix=url)
            self.assertNotContains(res, self.detail, msg_prefix=url)
        res = self.client.get('/')
        self.assertNotContains(res, '비밀카테고리')      # 사이드바 카테고리
        self.assertEqual(res.context['sidebar_total'], 1)
        self.assertEqual(self.client.get(self.detail).status_code, 404)
        self.assertEqual(self.client.get(reverse('add_comment_to_post', kwargs={'pk': self.private.pk})).status_code, 404)

    def test_not_counted(self):
        Post.objects.filter(pk=self.private.pk).update(view_count=0)
        self.client.get(self.detail, HTTP_X_REAL_IP='8.8.8.8')  # 404
        self.client.force_login(self.user)
        self.client.get(self.detail, HTTP_X_REAL_IP='8.8.8.8')  # 로그인 사용자는 원래 안 셈
        self.private.refresh_from_db()
        self.assertEqual(self.private.view_count, 0)

    def test_logged_in_sees_with_badge_and_button(self):
        self.client.force_login(self.user)
        res = self.client.get('/')
        self.assertContains(res, '비밀 글')
        self.assertContains(res, 'badge-private')
        res = self.client.get(self.detail)
        self.assertContains(res, '공개로 전환')
        self.assertContains(res, '<meta name="robots" content="noindex">')
        res = self.client.get(reverse('post_detail', kwargs={'pk': self.public.pk}))
        self.assertContains(res, '비공개로 전환')
        self.assertNotContains(self.client.get('/sitemap.xml'), self.detail)

    def test_button_hidden_for_anonymous(self):
        res = self.client.get(reverse('post_detail', kwargs={'pk': self.public.pk}))
        self.assertNotContains(res, '비공개로 전환')
        self.assertNotContains(res, self.toggle)

    def test_toggle(self):
        self.client.force_login(self.user)
        res = self.client.post(self.toggle)
        self.assertRedirects(res, reverse('post_detail', kwargs={'pk': self.public.pk}))
        self.public.refresh_from_db()
        self.assertTrue(self.public.is_private)
        self.client.post(self.toggle)
        self.public.refresh_from_db()
        self.assertFalse(self.public.is_private)

    def test_toggle_requires_login_and_post(self):
        res = self.client.post(self.toggle)
        self.assertEqual(res.status_code, 302)
        self.assertIn('/admin/login/', res['Location'])
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.toggle).status_code, 405)
        self.public.refresh_from_db()
        self.assertFalse(self.public.is_private)


# 글쓰기 카테고리 (기존 선택 / 새로 추가)
class PostCategoryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('tester', password='test-pass-123')
        self.client.force_login(self.user)
        Post.objects.create(author=self.user, title='기존', text='x', ctg='자바',
                            published_date=timezone.now() - timedelta(days=1))

    def save(self, **data):
        base = {'title': '새 글', 'text': '<p>본문</p>', 'new_ctg': ''}
        base.update(data)
        return self.client.post(reverse('post_new'), base)

    def test_choices_are_used_categories_and_new(self):
        res = self.client.get(reverse('post_new'))
        self.assertContains(res, '<option value="자바">')
        self.assertContains(res, '새 카테고리 추가')
        for unused in ['정리글', '소스', '백업']:  # 쓰이지 않는 옛 기본 카테고리는 안 보임
            self.assertNotContains(res, f'<option value="{unused}">')

    def test_existing_category(self):
        self.assertEqual(self.save(ctg='자바').status_code, 302)
        self.assertEqual(Post.objects.get(title='새 글').ctg, '자바')

    def test_new_category_created_and_listed(self):
        self.assertEqual(self.save(ctg='__new__', new_ctg='  파이썬   팁 ').status_code, 302)
        self.assertEqual(Post.objects.get(title='새 글').ctg, '파이썬 팁')
        self.assertContains(self.client.get(reverse('post_new')), '<option value="파이썬 팁">')

    def test_new_category_requires_name(self):
        res = self.save(ctg='__new__', new_ctg='   ')
        self.assertContains(res, '새 카테고리 이름을 입력하세요')
        self.assertFalse(Post.objects.filter(title='새 글').exists())

    def test_new_category_matches_existing_case_insensitively(self):
        Post.objects.create(author=self.user, title='영문', text='x', ctg='Django')
        self.save(ctg='__new__', new_ctg='django')
        self.assertEqual(Post.objects.get(title='새 글').ctg, 'Django')

    def test_unknown_choice_rejected(self):
        res = self.save(ctg='없는카테고리')
        self.assertEqual(res.status_code, 200)
        self.assertFalse(Post.objects.filter(title='새 글').exists())

    def test_edit_keeps_current_category(self):
        post = Post.objects.get(title='기존')
        res = self.client.get(reverse('post_edit', kwargs={'pk': post.pk}))
        self.assertContains(res, '<option value="자바" selected>')


# 카테고리 관리 (이름 변경 / 합치기)
class CategoryManageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('tester', password='test-pass-123')
        self.url = reverse('category_manage')
        past = timezone.now() - timedelta(days=1)
        for title, ctg, private in [('a', '기타', False), ('b', '메모', True), ('c', '메모', False)]:
            Post.objects.create(author=self.user, title=title, text='x', ctg=ctg,
                                published_date=past, is_private=private)
        Post.objects.create(author=self.user, title='draft', text='x', ctg='기타')  # 승인 대기

    def ctgs(self):
        return dict(Post.objects.values_list('title', 'ctg'))

    def test_requires_login(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.post(self.url, {'old': '기타', 'new': '해킹'})
        self.assertNotIn('해킹', self.ctgs().values())

    def test_lists_all_categories_with_counts(self):
        self.client.force_login(self.user)
        res = self.client.get(self.url)
        self.assertContains(res, '글 2개', count=2)  # 기타(공개+대기), 메모(비공개+공개)
        self.assertContains(self.client.get('/'), 'glyphicon-tags')  # 상단 메뉴 링크

    def test_rename(self):
        self.client.force_login(self.user)
        res = self.client.post(self.url, {'old': '기타', 'new': '  잡동사니 '}, follow=True)
        self.assertEqual(self.ctgs(), {'a': '잡동사니', 'b': '메모', 'c': '메모', 'draft': '잡동사니'})
        self.assertContains(res, "&#x27;기타&#x27; → &#x27;잡동사니&#x27; 로 바꿨습니다. (글 2개)")

    def test_merge_into_existing_case_insensitive(self):
        Post.objects.filter(ctg='메모').update(ctg='Memo')
        self.client.force_login(self.user)
        res = self.client.post(self.url, {'old': '기타', 'new': 'memo'}, follow=True)
        self.assertEqual(set(self.ctgs().values()), {'Memo'})
        self.assertContains(res, '합쳤습니다')

    def test_invalid_inputs(self):
        self.client.force_login(self.user)
        before = self.ctgs()
        for data, msg in [({'old': '기타', 'new': '  '}, '새 이름을 입력하세요'),
                          ({'old': '없는것', 'new': 'x'}, '찾을 수 없습니다'),
                          ({'old': '기타', 'new': 'x' * 51}, '너무 깁니다'),
                          ({'old': '기타', 'new': '기타'}, '이름이 같아서')]:
            self.assertContains(self.client.post(self.url, data, follow=True), msg)
        self.assertEqual(self.ctgs(), before)
