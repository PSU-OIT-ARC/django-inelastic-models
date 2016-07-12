from __future__ import unicode_literals
from __future__ import absolute_import

from django_dynamic_fixture import G
from django.test.runner import DiscoverRunner

from inelastic_models.models.test import Model, SearchFieldModel
from inelastic_models.receivers import get_search_models
from inelastic_models.utils.indexes import (refresh_search_indexes,
                                            clear_search_indexes)


class SearchTestRunner(DiscoverRunner):
    def setup_test_environment(self, **kwargs):
        super(SearchTestRunner, self).setup_test_environment(**kwargs)

        for model in get_search_models():
            model._search_meta().put_mapping()

class SearchBaseTestCase(object):
    """
    TBD
    """
    def _pre_setup(self):
        super(SearchBaseTestCase, self)._pre_setup()

        clear_search_indexes()
        refresh_search_indexes()

    def create_instance(self, **kwargs):
        params = {'test_list': None, 'test_m2m': []}
        params.update(kwargs)
        return G(Model, **params)
