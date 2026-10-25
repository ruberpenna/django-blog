import io
import logging
import os

from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger('django')

MAX_SIZE = 1920      # 긴 변 최대 픽셀
JPEG_QUALITY = 85


def shrink_image(data, name):
    """에디터에 올린 사진을 줄여서 (새 bytes, 새 파일명) 반환. 줄일 필요가 없거나 이미지가 아니면 None.
    - 긴 변을 MAX_SIZE 로 축소 (비율 유지)
    - 휴대폰 사진의 회전 정보를 적용한 뒤 EXIF(촬영 위치 GPS 등) 제거
    - GIF 는 움직이는 이미지일 수 있어 그대로 둠
    """
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError):
        return None  # 이미지가 아닌 첨부 파일
    fmt = img.format
    if fmt not in ('JPEG', 'PNG', 'WEBP', 'MPO'):  # MPO: 일부 휴대폰 JPEG
        return None

    has_exif = bool(img.getexif())
    too_big = max(img.size) > MAX_SIZE
    if not too_big and not has_exif:
        return None

    img = ImageOps.exif_transpose(img)  # 세로 사진이 눕지 않도록 회전 정보 반영
    if too_big:
        img.thumbnail((MAX_SIZE, MAX_SIZE), Image.LANCZOS)

    out = io.BytesIO()
    base, _ = os.path.splitext(name)
    if fmt in ('JPEG', 'MPO'):
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')
        img.save(out, 'JPEG', quality=JPEG_QUALITY, optimize=True, progressive=True)
        name = base + '.jpg'
    elif fmt == 'PNG':
        img.save(out, 'PNG', optimize=True)
    else:
        img.save(out, 'WEBP', quality=JPEG_QUALITY)
    result = out.getvalue()

    # 크기만 줄이지 않은(EXIF 만 지운) 경우 오히려 커지면 원본 유지
    if not too_big and len(result) >= len(data):
        return None
    return result, name


def shrink_attachment(sender, instance, **kwargs):
    """django-summernote 첨부 저장 직전에 사진을 줄임 (pre_save 시그널)"""
    f = instance.file
    if not f or getattr(f, '_committed', True):
        return  # 새로 올린 파일이 아니면 건드리지 않음
    data = f.read()
    try:
        shrunk = shrink_image(data, f.name)
    except Exception:
        logger.exception('사진 줄이기 실패, 원본 저장: %s', f.name)
        shrunk = None
    if shrunk is None:
        f.seek(0)
        return
    new_data, new_name = shrunk
    logger.info('사진 줄임: %s %dKB -> %dKB', f.name, len(data) // 1024, len(new_data) // 1024)
    instance.file = ContentFile(new_data, name=new_name)
