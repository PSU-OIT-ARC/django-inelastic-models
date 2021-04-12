from __future__ import unicode_literals
from __future__ import absolute_import

import datetime

import elasticsearch.exceptions
from django_dynamic_fixture import G
from django import test

from inelastic_models.utils.indexes import refresh_search_indexes
from inelastic_models.models.test import Model, SearchFieldModel

from .base import SearchBaseTestCase


class SearchFieldTestCase(SearchBaseTestCase, test.TestCase):
    """
    Validates behavior of 'search.SearchField' and derived types.
    """
    def setUp(self):
        super(SearchFieldTestCase, self).setUp()

        tm = self.create_instance(name='Test1',
                                  date=datetime.date(2015, 1, 1),
                                  email="test1@example.com")
        tm.save()
        tm2 = self.create_instance(name='Test2',
                                   date=None,
                                   email="test2@example.com")
        tm.save()

        tsfm = G(SearchFieldModel, related=tm)
        tsfm.save()

        tsfm.models.add(tm)
        tsfm.model_set.add(tm)
        tsfm.model_set.add(tm2)
        tsfm.save()

        refresh_search_indexes()

    def test_attribute_field(self):
        self.assertEqual(Model.search.count(), 2)
        self.assertEqual(set(h.name for h in Model.search.execute().hits),
                         set(['Test1', 'Test2']))

    def test_date_field(self):
        hits = Model.search.query('match', name='Test1').execute().hits
        self.assertEqual(len(hits), 1)

        # Check that dates are returned as datetime.date
        self.assertEqual(hits[0].date, datetime.date(2015, 1, 1))

        hits = Model.search.query('match', name='Test2').execute().hits
        self.assertEqual(len(hits), 1)

        # Check proper handling of None
        self.assertEqual(hits[0].date, None)

    def test_list_field(self):
        hits = SearchFieldModel.search.execute().hits
        self.assertEqual(len(hits), 1)
        self.assertIn('Test1', hits[0].model_list)

    def test_object_field(self):
        hits = SearchFieldModel.search.execute().hits
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].related.name, 'Test1')

    def test_reverse_multiobject_field(self):
        hits = SearchFieldModel.search.execute().hits

        self.assertEqual(len(hits), 1)
        self.assertEqual(len(hits[0].model_objects), 2)
        hit_names = set(h.name for h in hits[0].model_objects)
        self.assertIn('Test1', hit_names)
        self.assertIn('Test2', hit_names)

    def test_string_analyzed(self):
        query = Model.search.query('match', email='test1@example.com')
        self.assertEqual(len(query.execute().hits), 2)

    def test_string_not_indexed(self):
        mapping = Model._search_meta().get_mapping()
        self.assertFalse(mapping['properties']['test_email']['index'])

        # This field is not indexed:
        #   field will not be queryable.
        with self.assertRaises(elasticsearch.exceptions.TransportError):
            query = Model.search.query('match', test_email='test1@example.com')
            query.execute()
