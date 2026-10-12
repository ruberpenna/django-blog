from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from .models import Post, Comment
from .forms import PostForm, CommentForm
from .notify import notify_new_comment
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.views.decorators.cache import cache_page
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

# 댓글 등록페이지
def add_comment_to_post(request, pk):
    post = get_visible_post(request, pk)
    if request.method == "POST":
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.post = post
            comment.save()
            notify_new_comment(request, comment)
            return redirect('post_detail', pk=post.pk)
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
