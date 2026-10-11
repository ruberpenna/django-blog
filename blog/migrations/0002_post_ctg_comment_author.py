# 운영 DB에는 수동으로 먼저 반영돼 있던 변경을 마이그레이션으로 기록
# (운영 DB에서는 migrate blog 0002 --fake 로 적용 처리)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('blog', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='post',
            name='ctg',
            field=models.CharField(default='기타', max_length=50),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='comment',
            name='author',
            field=models.CharField(max_length=20),
        ),
    ]
