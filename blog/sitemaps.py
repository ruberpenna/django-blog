from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from django.utils import timezone
from .models import Post

# 발행된 글 목록 (sitemap.xml)
class PostSitemap(Sitemap):
    changefreq = 'monthly'
    priority = 0.8

    def items(self):
        return Post.objects.filter(published_date__lte=timezone.now()).order_by('-published_date')

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
