from django.apps import AppConfig
from django.db.models.signals import pre_save


class BlogConfig(AppConfig):
    name = 'blog'

    def ready(self):
        # 에디터(summernote)로 올린 사진을 저장 직전에 줄이고 EXIF(위치 정보 등) 제거
        from django_summernote.utils import get_attachment_model
        from .images import shrink_attachment
        pre_save.connect(shrink_attachment, sender=get_attachment_model(), dispatch_uid='blog_shrink_attachment')
