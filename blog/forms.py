import re
import time

from django import forms
from django.core import signing
from .models import Post, Comment, resolve_category
from django_summernote.widgets import SummernoteWidget
import logging

logger = logging.getLogger('django')

# 포스트 폼
class PostForm(forms.ModelForm):
    NEW_CATEGORY = '__new__'  # "새 카테고리 추가" 선택값

    # 기존 카테고리 선택 + "새 카테고리 추가" (목록은 __init__ 에서 DB 기준으로 채움)
    ctg = forms.ChoiceField(label='카테고리', widget=forms.Select(attrs={'class': 'form-control'}))
    new_ctg = forms.CharField(label='새 카테고리', required=False, max_length=50,
                              widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '새 카테고리 이름',
                                                            'maxlength': '50'}))

    class Meta:
        model = Post
        fields = ('ctg', 'title', 'text')
        labels = {'title': '제목', 'text': '본문'}
        widgets = {
        	'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '제목을 입력하세요', 'maxlength': '100'}),
        	'text': SummernoteWidget(attrs={'summernote': {'width': '100%', 'height': '520px'}}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 글에 쓰이고 있는 카테고리 + "새 카테고리 추가" (카테고리 이름 변경/합치기는 카테고리 관리 화면에서)
        self.category_names = Post.objects.category_names()
        self.fields['ctg'].choices = [(n, n) for n in self.category_names] + [(self.NEW_CATEGORY, '+ 새 카테고리 추가…')]

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('ctg') != self.NEW_CATEGORY:
            return cleaned
        name = resolve_category(cleaned.get('new_ctg'), self.category_names)
        if not name:
            self.add_error('new_ctg', '새 카테고리 이름을 입력하세요.')
        else:
            cleaned['ctg'] = name
        return cleaned

# 댓글 폼 (스팸 방지: 숨김 입력칸, 작성 시간 검사, 링크 개수 제한)
class CommentForm(forms.ModelForm):
    MIN_SECONDS = 3        # 폼을 연 뒤 이 시간 안에 제출하면 봇으로 간주
    MAX_AGE = 60 * 60 * 24  # 폼 유효 시간
    MAX_LINKS = 2
    LINK_RE = re.compile(r'(?:https?://|www\.)\S+', re.I)  # https://www.a.com 도 링크 1개로 셈

    # 사람에게는 보이지 않는 칸. 봇이 채우면 저장하지 않음
    # (website, url 같은 이름은 브라우저 자동완성이 채울 수 있어 피함)
    leave_blank = forms.CharField(required=False, label='이 칸은 비워 두세요',
                                  widget=forms.TextInput(attrs={'autocomplete': 'off', 'tabindex': '-1'}))
    # 폼을 연 시각 (서명해서 위조 방지)
    ts = forms.CharField(required=False, widget=forms.HiddenInput)

    class Meta:
        model = Comment
        fields = ('author', 'text')
        labels = {'author': '작성자', 'text': '내용'}
        widgets = {
        	'author': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '작성자', 'maxlength': '20'}),
        	'text': forms.Textarea(attrs={'class': 'form-control', 'placeholder': '내용', 'maxlength': '300'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.is_bot = False
        if not self.is_bound:
            self.initial['ts'] = self.new_timestamp()

    @staticmethod
    def new_timestamp():
        return signing.dumps(time.time(), salt='comment-form')

    def renew_timestamp(self):
        """오류로 폼을 다시 보여줄 때 새 시각을 넣음 (만료된 값을 다시 보내 계속 실패하지 않게)"""
        self.data = self.data.copy()
        self.data['ts'] = self.new_timestamp()

    def clean_text(self):
        text = self.cleaned_data['text']
        if len(self.LINK_RE.findall(text)) > self.MAX_LINKS:
            raise forms.ValidationError(f'링크는 {self.MAX_LINKS}개까지만 넣을 수 있습니다.')
        return text

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('leave_blank'):
            self.is_bot = True
            return cleaned
        try:
            opened = signing.loads(cleaned.get('ts') or '', salt='comment-form', max_age=self.MAX_AGE)
        except signing.BadSignature:  # 없음, 위조, 만료 (SignatureExpired 포함)
            raise forms.ValidationError('페이지를 새로고침한 뒤 다시 등록해 주세요.')
        if time.time() - opened < self.MIN_SECONDS:
            raise forms.ValidationError('너무 빨리 등록했습니다. 잠시 후 다시 시도해 주세요.')
        return cleaned