from __future__ import unicode_literals
from __future__ import absolute_import

import logging

from inelastic_models.management.commands import IndexCommand

logger = logging.getLogger(__name__)


class Command(IndexCommand):
    """
    TBD
    """
    help = 'Updates the index mapping, if necessary. This operation destroys the existing index.'

    def handle_operation(self, search, queryset):
        if search.check_mapping():
            logger.info("Mapping '{}' does not require migration.".format(search))
            return

        logger.info("Migrating new or existing mapping '{}'...".format(search))
        search.put_mapping()

        logger.info("(Re-)Indexing mapping '{}'...".format(search))
        search.index_qs(queryset)
