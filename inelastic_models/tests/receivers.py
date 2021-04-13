from django_dynamic_fixture import G
from django.db import transaction
from django import test

from inelastic_models.utils.indexes import refresh_search_indexes
from inelastic_models.models.test import Model, TEST_MODEL_EXCLUDE_NAME
from inelastic_models.receivers import get_search_models, suspended_updates

from .base import SearchBaseTestCase


class SearchPostSaveTestCase(SearchBaseTestCase, test.TestCase):
    """
    TBD
    """
    def setUp(self):
        super().setUp()

        self.assertIn(Model, get_search_models())

    def test_post_save(self):
        self.assertEqual(Model.search.count(), 0)

        tm = self.create_instance(name="Test1")
        refresh_search_indexes()
        self.assertEqual(Model.search.count(), 1)

    def test_qs_exclusion(self):
        self.assertEqual(Model.search.count(), 0)

        tm = Model(name=TEST_MODEL_EXCLUDE_NAME)
        tm.save()
        refresh_search_indexes()
        self.assertEqual(Model.search.count(), 0)

        tm.name="Test3"
        tm.save()
        refresh_search_indexes()
        self.assertEqual(Model.search.count(), 1)

        tm.name=TEST_MODEL_EXCLUDE_NAME
        tm.save()
        refresh_search_indexes()
        self.assertEqual(Model.search.count(), 0)

    def test_post_delete(self):
        tm = Model(name="Test4")
        tm.save()
        refresh_search_indexes()
        self.assertEqual(Model.search.count(), 1)

        tm.delete()
        refresh_search_indexes()
        self.assertEqual(Model.search.count(), 0)

    def test_m2m(self):
        tm = Model(name="Test4")
        tm.save()
        refresh_search_indexes()
        self.assertEqual(Model.search.count(), 1)
        self.assertEqual(Model.search.execute().hits[0].count_m2m, '0')

        tm.test_m2m.create()
        refresh_search_indexes()
        self.assertEqual(Model.search.count(), 1)
        self.assertEqual(Model.search.execute().hits[0].count_m2m, '1')

        tm.test_m2m.clear()
        refresh_search_indexes()
        self.assertEqual(Model.search.count(), 1)
        self.assertEqual(Model.search.execute().hits[0].count_m2m, '0')

    def test_suspended_updates(self):
        self.assertEqual(Model.search.count(), 0)

        with suspended_updates(models=[Model]):
            tm = self.create_instance(name="Test2")
            refresh_search_indexes()
            self.assertEqual(Model.search.count(), 0)

        refresh_search_indexes()
        self.assertEqual(Model.search.count(), 1)
