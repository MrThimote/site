# Generated by Django 2.1.7 on 2019-02-16 18:18

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('schools', '0002_schools_options'),
    ]

    operations = [
        migrations.AlterField(
            model_name='school',
            name='imported',
            field=models.BooleanField(blank=True, default=False),
        ),
    ]
