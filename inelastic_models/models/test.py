from __future__ import unicode_literals
from __future__ import absolute_import

import six

from django.utils.encoding import python_2_unicode_compatible
from django.db import models

from ..indexes import SearchMixin, Search
from ..fields import NGramField, ListField, ObjectField, MultiObjectField

TEST_MODEL_EXCLUDE_NAME = 'NO'


@python_2_unicode_compatible
class Model(SearchMixin, models.Model):
    name = models.CharField(max_length=256)
    modified_on = models.DateTimeField(auto_now=True)
    date = models.DateField(null=True, blank=True)
    test_list = models.ForeignKey('inelastic_models.SearchFieldModel',
                                  related_name='models',
                                  null=True, blank=True)
    test_m2m = models.ManyToManyField('inelastic_models.SearchFieldModel', blank=True)
    email = models.EmailField(blank=True)
    non_indexed_field = models.CharField(max_length=16, blank=True)

    @property
    def count_m2m(self):
        return six.text_type(self.test_m2m.count())

    def __str__(self):
        return self.name

    class Meta:
        app_label = 'inelastic_models'

class ModelSearch(Search):
    attribute_fields = ['name', 'date', 'email', 'count_m2m']
    other_fields = {
        'test_ngram': NGramField('name'),
    }

    def get_base_qs(self):
        return self.model.objects.exclude(name=TEST_MODEL_EXCLUDE_NAME)

ModelSearch.bind_to_model(Model)

@python_2_unicode_compatible
class SearchFieldModel(SearchMixin, models.Model):
    modified_on = models.DateTimeField(auto_now=True)
    related = models.ForeignKey('inelastic_models.Model', null=True, blank=True)

    def __str__(self):
        return six.text_type("Related: %s" % (self.related))

    class Meta:
        app_label = 'inelastic_models'

class SearchFieldModelSearch(Search):
    other_fields = {
        'model_list': ListField('models'),
        'related': ObjectField(
            'related', attribute_fields=['name', 'modified_on']),
        'model_objects': MultiObjectField(
            'model_set', attribute_fields=['name','modified_on']),
    }

SearchFieldModelSearch.bind_to_model(SearchFieldModel)
