from django_dynamic_fixture import G
from django.test.runner import DiscoverRunner

from inelastic_models.models.test import Model, SearchFieldModel
from inelastic_models.receivers import get_search_models


class SearchTestRunner(DiscoverRunner):
    """
    TBD
    """
    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)

        if not self.keepdb:
            for model in get_search_models():
                model._search_meta().put_mapping()


class SearchBaseTestCase(object):
    """
    TBD
    """
    def _pre_setup(self):
        super()._pre_setup()

        for model in get_search_models():
            model._search_meta().bulk_clear()

    def create_instance(self, **kwargs):
        params = {'test_list': None, 'test_m2m': []}
        params.update(kwargs)
        return G(Model, **params)
