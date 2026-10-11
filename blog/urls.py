from django.urls import path, include
from django.conf.urls import url
from django.conf.urls.static import static
from django.conf import settings
from . import views

urlpatterns = [
    path('', views.post_list, name='post_list'), # 글 목록
    path('srch/', views.post_srch, name='post_srch'), # 검색 함수
    path('post/<int:pk>/', views.post_detail, name='post_detail'), # 글 상세
    path('post/new', views.post_new, name='post_new'), # 글 작성
    path('post/<int:pk>/edit/', views.post_edit, name='post_edit'), # 글 수정
    path('summernote/', include('django_summernote.urls')), # 에디터

    url(r'^drafts/$', views.post_draft_list, name='post_draft_list'), # 임시글 목록
    url(r'^post/(?P<pk>\d+)/publish/$', views.post_publish, name='post_publish'), # 임시글 승인
    url(r'^post/(?P<pk>\d+)/comment/$', views.add_comment_to_post, name='add_comment_to_post'), # 댓글 작성
    url(r'^post/(?P<pk>\d+)/remove/$', views.post_remove, name='post_remove'), # 글 삭제
    url(r'^comment/(?P<pk>\d+)/approve/$', views.comment_approve, name='comment_approve'), # 댓글 승인
	url(r'^comment/(?P<pk>\d+)/remove/$', views.comment_remove, name='comment_remove'), # 댓글 삭제
]

urlpatterns += \
    static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)