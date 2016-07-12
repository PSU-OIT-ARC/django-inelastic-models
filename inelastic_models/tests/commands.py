from __future__ import unicode_literals
from __future__ import absolute_import

import datetime
import logging
import six

from django_dynamic_fixture import G
from django.core.management import call_command
from django import test

from inelastic_models.utils.indexes import refresh_search_indexes
from inelastic_models.models.test import Model, ModelSearch
from inelastic_models.receivers import suspended_updates
from .base import SearchBaseTestCase

logger = logging.getLogger(__name__)


class CommandTestCaseMixin(SearchBaseTestCase):
    """
    TBD
    """
    command_name = None

    def get_command_args(self):
        raise NotImplementedError

    def check_command_response(self, response, **kwargs):
        if kwargs.get('error', None) is not None:
            print("\nCommand errors detected.\n%s" % (kwargs.pop('error')))
            self.fail("Command generated errors.")

    def test_command(self):
        if hasattr(self, 'prepare_command'):
            self.prepare_command()

        (args, kwargs) = self.get_command_args()
        logger.info("Executing command: '%s' '%s'" % (args, kwargs))
        response_buffer = six.StringIO()
        error = None

        try:
            kwargs.update({'stdout': response_buffer})
            call_command(self.command_name, *args, **kwargs)
        except Exception as e:
            import traceback
            traceback.print_exc()
            error = e

        response = response_buffer.getvalue().strip()
        self.check_command_response(response, error=error)

class SearchCommandTestCase(CommandTestCaseMixin):
    update_limit = 100

    def setUp(self):
        super(SearchCommandTestCase, self).setUp()

        with suspended_updates(models=[Model], permanent=True):
            self.instance = G(Model, name='Test1')

        self.assertEqual(Model.search.count(), 0)

    def get_command_args(self):
        (args, kwargs) = (('inelastic_models.model',), {})

        kwargs['since'] = datetime.date.today().strftime('%Y-%m-%d')
        kwargs['until'] = (datetime.date.today() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        kwargs['limit'] = self.update_limit

        return (args, kwargs)

class CreateIndexCommandTestCase(SearchCommandTestCase, test.TestCase):
    command_name = 'create_index'

    def check_command_response(self, response, **kwargs):
        super(SearchCommandTestCase, self).check_command_response(
            response, **kwargs)

        refresh_search_indexes()
        self.assertEqual(Model.search.count(), 1)

class UpdateIndexCommandTestCase(SearchCommandTestCase, test.TestCase):
    command_name = 'update_index'

    def check_command_response(self, response, **kwargs):
        super(SearchCommandTestCase, self).check_command_response(
            response, **kwargs)

        G(Model, name='Test2')
        refresh_search_indexes()
        self.assertEqual(Model.search.count(), 2)

class MigrateIndexCommandTestCase(SearchCommandTestCase, test.TestCase):
    command_name = 'migrate_index'

    def setUp(self):
        super(MigrateIndexCommandTestCase, self).setUp()

        G(Model, name='Test2', non_indexed_field='Hack the Gibson.')
        ModelSearch.attribute_fields.append('non_indexed_field')

    def check_command_response(self, response, **kwargs):
        super(SearchCommandTestCase, self).check_command_response(
            response, **kwargs)

        refresh_search_indexes()
        self.assertEqual(Model.search.query('match', test_ngram='Test').count(), 2)
        self.assertEqual(Model.search.query('match', non_indexed_field='Hack the Gibson.').count(), 1)
