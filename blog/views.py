from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from .models import Post, Comment
from .forms import PostForm, CommentForm
from .notify import notify_new_comment
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.views.decorators.cache import cache_page
import ipaddress
import logging

# 로거 선언
logger = logging.getLogger('django')

# Create your views here.

# 글 리스트
def post_list(request):
    posts = Post.objects.filter(published_date__lte=timezone.now()).order_by('-published_date')
    
    #blog_list = Post.objects.all()
    # logger.info(blog_list)

    paginator = Paginator(posts, 10)
    page = request.GET.get('page')
    lists = paginator.get_page(page)
    return render(request, 'blog/post_list.html', {'posts': posts, 'lists': lists})

# 발행된 글만 조회 (승인 대기/예약 글은 로그인한 사용자만, 그 외에는 404)
def get_visible_post(request, pk):
    posts = Post.objects.all()
    if not request.user.is_authenticated:
        posts = posts.filter(published_date__lte=timezone.now())
    return get_object_or_404(posts, pk=pk)

# 글 상세
def post_detail(request, pk):
    post = get_visible_post(request, pk)
    meta = {
        'type': 'article',
        'title': post.title,
        'description': post.summary(),
        'image': post.first_image(),
        'noindex': not post.published_date,  # 승인 대기 글은 검색엔진 제외
    }
    return render(request, 'blog/post_detail.html', {'post': post, 'meta': meta})

# 글 등록
@login_required
def post_new(request):
    if request.method == "POST":
        form = PostForm(request.POST)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            #post.published_date = timezone.now()
            post.save()
            return redirect('post_detail', pk=post.pk)
    else:
        form = PostForm()
    return render(request, 'blog/post_edit.html', {'form': form})

# 글 수정
@login_required
def post_edit(request, pk):
    post = get_object_or_404(Post, pk=pk)
    if request.method == "POST":
        form = PostForm(request.POST, instance=post)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            #post.published_date = timezone.now()
            post.save()
            return redirect('post_detail', pk=post.pk)
    else:
        form = PostForm(instance=post)
    return render(request, 'blog/post_edit.html', {'form': form})

# 승인 대기 글/댓글 목록
@login_required
def post_draft_list(request):
    posts = Post.objects.filter(published_date__isnull=True).order_by('created_date')
    comms = Comment.objects.filter(approved_comment=False).order_by('created_date')
    return render(request, 'blog/post_draft_list.html', {'posts': posts, 'comms': comms})

# 대기글 승인
@login_required
@require_POST
def post_publish(request, pk):
    post = get_object_or_404(Post, pk=pk)
    post.publish()
    return redirect('post_detail', pk=pk)

# 글 삭제
@login_required
@require_POST
def post_remove(request, pk):
    post = get_object_or_404(Post, pk=pk)
    post.delete()
    return redirect('post_list')

# 방문자 IP: NPM -> Caddy -> Waitress 를 거침
# 운영에서는 Caddy 가 넣는 X-Real-IP 사용 (Waitress 가 X-Forwarded-For 를 지우기 때문)
# 없으면 X-Forwarded-For 오른쪽부터 내부망이 아닌 첫 주소 (왼쪽 값은 방문자가 위조할 수 있음)
def get_client_ip(request):
    real_ip = request.META.get('HTTP_X_REAL_IP', '').strip()
    if real_ip:
        return real_ip
    chain = [ip.strip() for ip in request.META.get('HTTP_X_FORWARDED_FOR', '').split(',') if ip.strip()]
    for ip in reversed(chain):
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if not (addr.is_private or addr.is_loopback):
            return ip
    return request.META.get('REMOTE_ADDR', '')

COMMENT_RATE_LIMIT = 3          # 같은 IP 에서
COMMENT_RATE_WINDOW = 60 * 10   # 10분에 3개까지

# 이번 작성을 횟수에 더하고, 제한을 넘었으면 True
# (incr 결과로 판정해야 동시 요청이 같은 값을 읽고 함께 통과하지 않음)
def comment_rate_limited(request):
    key = 'comment-rate:' + get_client_ip(request)
    cache.add(key, 0, COMMENT_RATE_WINDOW)
    try:
        count = cache.incr(key)
    except ValueError:  # add 와 incr 사이에 만료된 경우
        cache.set(key, 1, COMMENT_RATE_WINDOW)
        count = 1
    return count > COMMENT_RATE_LIMIT

# 댓글 등록페이지
def add_comment_to_post(request, pk):
    post = get_visible_post(request, pk)
    if request.method == "POST":
        form = CommentForm(request.POST)
        if form.is_valid():
            if form.is_bot:
                # 봇에게는 성공한 것처럼 보이고 저장하지 않음
                logger.info('스팸 댓글 차단(숨김 입력칸): post=%s ip=%s', post.pk, get_client_ip(request))
                return redirect('post_detail', pk=post.pk)
            if comment_rate_limited(request):
                form.add_error(None, '짧은 시간에 댓글을 너무 많이 등록했습니다. 10분 뒤에 다시 시도해 주세요.')
                form.renew_timestamp()
                return render(request, 'blog/add_comment_to_post.html', {'form': form}, status=429)
            comment = form.save(commit=False)
            comment.post = post
            comment.save()
            notify_new_comment(request, comment)
            return redirect('post_detail', pk=post.pk)
        form.renew_timestamp()
    else:
        form = CommentForm()
    return render(request, 'blog/add_comment_to_post.html', {'form': form})

# 댓글 승인
@login_required
@require_POST
def comment_approve(request, pk):
    comment = get_object_or_404(Comment, pk=pk)
    comment.approve()
    return redirect('post_detail', pk=comment.post.pk)

# 댓글 삭제
@login_required
@require_POST
def comment_remove(request, pk):
    comment = get_object_or_404(Comment, pk=pk)
    comment.delete()
    return redirect('post_detail', pk=comment.post.pk)

# 검색 함수
def post_srch(request):
    page = request.GET.get('page', '1') # 페이지
    kwd = request.GET.get('kwd', '') # 검색어
    ctg = request.GET.get('ctg', '') # 카테고리
    posts = Post.objects.filter(published_date__lte=timezone.now()).order_by('-published_date')
    if ctg:
        posts = posts.filter(ctg=ctg)
    if kwd:
        posts = posts.filter(
            Q(title__icontains=kwd) | # 제목 검색
            Q(text__icontains=kwd) # 내용 검색
        ).distinct()
    paginator = Paginator(posts, 10) # 페이지당 10개씩
    lists = paginator.get_page(page)
    context = {'lists': lists, 'page': page, 'kwd': kwd, 'ctg': ctg}
    return render(request, 'blog/post_list.html', context)
# 검색엔진 수집 규칙
@cache_page(60 * 60)
def robots_txt(request):
    lines = [
        'User-agent: *',
        'Disallow: /admin/',
        'Disallow: /drafts/',
        'Disallow: /summernote/',
        'Disallow: /srch/?kwd=',
        '',
        'Sitemap: ' + request.build_absolute_uri('/sitemap.xml'),
    ]
    return HttpResponse('\n'.join(lines) + '\n', content_type='text/plain')
