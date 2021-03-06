# -*- coding: utf-8 -*-
# Generated by Django 1.9.5 on 2016-06-02 18:23
from __future__ import unicode_literals

from django.db import migrations
import prologin.utils.storage
import prologin.utils.models
import users.models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_preferred_language_not_null'),
    ]

    operations = [
        migrations.AlterField(
            model_name='prologinuser',
            name='avatar',
            field=prologin.utils.models.ResizeOnSaveImageField(blank=True, fit_into=(220, 220), storage=prologin.utils.storage.OverwriteStorage(), upload_to=users.models.ProloginUser.upload_avatar_to, verbose_name='Profile picture'),
        ),
        migrations.AlterField(
            model_name='prologinuser',
            name='picture',
            field=prologin.utils.models.ResizeOnSaveImageField(blank=True, fit_into=(220, 220), storage=prologin.utils.storage.OverwriteStorage(), upload_to=users.models.ProloginUser.upload_picture_to, verbose_name='Official member picture'),
        ),
    ]
