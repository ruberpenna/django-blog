import html
import re

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import Truncator

class PostQuerySet(models.QuerySet):
    def visible_to(self, user):
        """목록/검색/사이드바에 보여줄 글: 발행된 글. 비공개 글은 로그인한 사용자에게만"""
        posts = self.filter(published_date__lte=timezone.now())
        if not user.is_authenticated:
            posts = posts.filter(is_private=False)
        return posts

    def category_names(self):
        """글에 쓰이고 있는 카테고리 이름 (가나다순)"""
        return sorted(set(self.exclude(ctg='').values_list('ctg', flat=True)))


def resolve_category(name, existing):
    """입력한 카테고리 이름 정리: 공백 정리, 대소문자만 다른 기존 이름이 있으면 그 이름 사용.
    빈 이름이면 '' 반환"""
    name = ' '.join((name or '').split())
    return {c.lower(): c for c in existing}.get(name.lower(), name)


# 블로그 포스트 DB 세팅
class Post(models.Model):
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    text = models.TextField()
    created_date = models.DateTimeField(default=timezone.now)
    published_date = models.DateTimeField(blank=True, null=True)
    ctg = models.CharField(max_length=50)
    view_count = models.PositiveIntegerField('조회수', default=0)
    is_private = models.BooleanField('비공개', default=False)  # True 면 로그인한 사용자만 볼 수 있음

    objects = PostQuerySet.as_manager()

    def publish(self):
        self.published_date = timezone.now()
        self.save()

    def __str__(self):
        return f'{self.title} | {self.ctg}'

    def get_absolute_url(self):
        return reverse('post_detail', kwargs={'pk': self.pk})

    # 검색엔진/공유 미리보기용 요약 (HTML 태그 제거)
    def summary(self, length=150):
        # 태그를 공백으로 바꿔서 <br>, <p> 경계의 단어가 붙지 않게 함
        text = ' '.join(html.unescape(re.sub(r'<[^>]+>', ' ', self.text or '')).split())
        return Truncator(text).chars(length)

    # 본문의 첫 번째 이미지 주소 (공유 미리보기 썸네일)
    def first_image(self):
        match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', self.text or '')
        return match.group(1) if match else ''

    def approved_comments(self):
        return self.comments.filter(approved_comment=True)

# 블로그 댓글 DB 세팅
class Comment(models.Model):
    post = models.ForeignKey('blog.Post', on_delete=models.CASCADE, related_name='comments')
    author = models.CharField(max_length=20)
    text = models.TextField()
    created_date = models.DateTimeField(default=timezone.now)
    approved_comment = models.BooleanField(default=False)

    def approve(self):
        self.approved_comment = True
        self.save()

    def __str__(self):
        return self.text
