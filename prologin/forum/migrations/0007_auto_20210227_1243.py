# Generated by Django 2.2.19 on 2021-02-27 11:43

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('forum', '0006_notification_thread'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='notificationlist',
            name='last_post',
        ),
        migrations.AddField(
            model_name='notificationlist',
            name='notification_count',
            field=models.PositiveIntegerField(blank=True, default=0, editable=False, verbose_name='Number of notifications'),
        ),
    ]
