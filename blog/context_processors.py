from django.db.models import Count
from django.utils import timezone
from .models import Post

# 사이드바 공통 데이터 (카테고리 목록, 최근 글)
def sidebar(request):
    published = Post.objects.filter(published_date__lte=timezone.now())
    categories = published.values('ctg').annotate(cnt=Count('id')).order_by('ctg')
    recent_posts = published.order_by('-published_date')[:5]
    return {
        'sidebar_categories': categories,
        'sidebar_total': published.count(),
        'sidebar_recent': recent_posts,
    }
