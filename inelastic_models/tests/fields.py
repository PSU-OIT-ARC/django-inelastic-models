import datetime

import elasticsearch.exceptions
from django_dynamic_fixture import G
from django import test

from inelastic_models.models.test import Model, SearchFieldModel
from inelastic_models.tests.base import SearchBaseTestCase


class SearchFieldTestCase(SearchBaseTestCase, test.TestCase):
    """
    Validates behavior of 'search.SearchField' and derived types.
    """
    def setUp(self):
        super().setUp()

        tm = self.create_instance(name='Test1 one two three',
                                  email="test1@example.com",
                                  date=datetime.date(2015, 1, 1))

        tm.save()
        tm2 = self.create_instance(name='Test2 four five six',
                                   email="test2@example.com",
                                   date=None)
        tm.save()

        tsfm = G(SearchFieldModel, related=tm)
        tsfm.save()

        tsfm.models.add(tm)
        tsfm.model_set.add(tm)
        tsfm.model_set.add(tm2)
        tsfm.save()

    def test_attribute_field(self):
        self.assertEqual(Model.search.count(), 2)
        self.assertEqual(set(h.name for h in Model.search.execute().hits),
                         set(['Test1 one two three', 'Test2 four five six']))

    def test_date_field(self):
        hits = Model.search.query('match', name='Test1 one two three').execute().hits
        self.assertEqual(len(hits), 1)

        # Check that dates are returned as datetime.date
        self.assertEqual(hits[0].date, datetime.date(2015, 1, 1))

        hits = Model.search.query('match', name='Test2 four five six').execute().hits
        self.assertEqual(len(hits), 1)

        # Check proper handling of None
        self.assertEqual(hits[0].date, None)

    def test_list_field(self):
        hits = SearchFieldModel.search.execute().hits
        self.assertEqual(len(hits), 1)
        self.assertIn('Test1 one two three', hits[0].model_list)

    def test_object_field(self):
        hits = SearchFieldModel.search.execute().hits
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].related.name, 'Test1 one two three')

    def test_reverse_multiobject_field(self):
        hits = SearchFieldModel.search.execute().hits

        self.assertEqual(len(hits), 1)
        self.assertEqual(len(hits[0].model_objects), 2)
        hit_names = set(h.name for h in hits[0].model_objects)
        self.assertIn('Test1 one two three', hit_names)
        self.assertIn('Test2 four five six', hit_names)

    def test_char_field(self):
        query = Model.search.query('term', name="Test1")
        self.assertEqual(len(query.execute().hits), 0)

        query = Model.search.query('match', name="Test1")
        self.assertEqual(len(query.execute().hits), 0)

        query = Model.search.query('term', name="Test1 one two three")
        self.assertEqual(len(query.execute().hits), 1)

        query = Model.search
        query.aggs.bucket('keyword', 'terms', field='name')
        self.assertNotEqual(query.execute().aggregations.to_dict(), {})

        mapping = Model._search_meta().get_mapping()
        self.assertFalse('tokenizer' in mapping['properties']['name'])

    def test_text_field(self):
        query = Model.search.query('match', text='one four')
        self.assertEqual(len(query.execute().hits), 2)

        # text mapping types don't support aggregations, sorting
        with self.assertRaises(elasticsearch.exceptions.BadRequestError):
            query = Model.search
            query.aggs.bucket('text', 'terms', field='text')
            query.execute()

    def test_ngram_field(self):
        query = Model.search.query('match', ngram='est')
        self.assertEqual(len(query.execute().hits), 2)
