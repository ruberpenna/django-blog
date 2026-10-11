from django import forms
from .models import Post, Comment
from django_summernote.widgets import SummernoteWidget
import logging

logger = logging.getLogger('django')

# 포스트 폼
class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ('ctg', 'title', 'text')
        ctgs = [('정리글', '정리글'), ('소스', '소스'), ('백업', '백업'), ('기타', '기타')]
        labels = {'ctg': '카테고리', 'title': '제목', 'text': '본문'}
        widgets = {
            'ctg': forms.Select(attrs={'class':'form-control'}, choices=ctgs),
        	'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '제목을 입력하세요', 'maxlength': '100'}),
        	'text': SummernoteWidget(attrs={'summernote': {'width': '100%', 'height': '520px'}}),
        }

# 댓글 폼
class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ('author', 'text')
        labels = {'author': '작성자', 'text': '내용'}
        widgets = {
        	'author': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '작성자', 'maxlength': '20'}),
        	'text': forms.Textarea(attrs={'class': 'form-control', 'placeholder': '내용', 'maxlength': '300'}),
        }