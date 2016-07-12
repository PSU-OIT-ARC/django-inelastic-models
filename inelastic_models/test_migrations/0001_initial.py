# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import inelastic_models.indexes


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Model',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=256)),
                ('modified_on', models.DateTimeField(auto_now=True)),
                ('date', models.DateField(null=True, blank=True)),
                ('email', models.EmailField(max_length=254, blank=True)),
                ('non_indexed_field', models.CharField(max_length=16, blank=True)),
            ],
            bases=(inelastic_models.indexes.SearchMixin, models.Model),
        ),
        migrations.CreateModel(
            name='SearchFieldModel',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('modified_on', models.DateTimeField(auto_now=True)),
                ('related', models.ForeignKey(blank=True, to='inelastic_models.Model', null=True)),
            ],
            bases=(inelastic_models.indexes.SearchMixin, models.Model),
        ),
        migrations.AddField(
            model_name='model',
            name='test_list',
            field=models.ForeignKey(related_name='models', blank=True, to='inelastic_models.SearchFieldModel', null=True),
        ),
        migrations.AddField(
            model_name='model',
            name='test_m2m',
            field=models.ManyToManyField(to='inelastic_models.SearchFieldModel', blank=True),
        ),
    ]
