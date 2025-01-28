# Generated by Django 5.0.3 on 2024-09-07 08:20

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0002_alter_bugjob_id"),
    ]

    operations = [
        migrations.CreateModel(
            name="BugJobCategory",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
            ],
        ),
        migrations.AlterField(
            model_name="bugjob",
            name="experience",
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name="bugjob",
            name="category",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="jobs",
                to="jobs.bugjobcategory",
            ),
        ),
    ]
