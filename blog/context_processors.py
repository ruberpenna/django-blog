from django.db.models import Count
from .models import Post

# 사이드바 공통 데이터 (카테고리 목록, 최근 글)
def sidebar(request):
    published = Post.objects.visible_to(request.user)
    categories = published.values('ctg').annotate(cnt=Count('id')).order_by('ctg')
    recent_posts = published.order_by('-published_date')[:5]
    popular_posts = published.filter(view_count__gt=0).order_by('-view_count', '-published_date')[:5]
    return {
        'sidebar_categories': categories,
        'sidebar_total': published.count(),
        'sidebar_recent': recent_posts,
        'sidebar_popular': popular_posts,
    }
