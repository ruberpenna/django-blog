from django.contrib import admin
from .models import Post, Comment

# Register your models here.
@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('title', 'ctg', 'published_date', 'view_count')
    list_filter = ('ctg',)
    search_fields = ('title',)
    ordering = ('-published_date',)

admin.site.register(Comment)
