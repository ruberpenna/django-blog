from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.contrib.auth.models import AnonymousUser
from .models import Post

# 발행된 글 목록 (sitemap.xml)
class PostSitemap(Sitemap):
    changefreq = 'monthly'
    priority = 0.8

    def items(self):
        return Post.objects.visible_to(AnonymousUser()).order_by('-published_date')  # 공개 글만

    def lastmod(self, post):
        return post.published_date

# 메인 페이지
class StaticSitemap(Sitemap):
    changefreq = 'daily'
    priority = 1.0

    def items(self):
        return ['post_list']

    def location(self, item):
        return reverse(item)
