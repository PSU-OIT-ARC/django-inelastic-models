from __future__ import unicode_literals
from __future__ import absolute_import

import logging

from inelastic_models.management.commands import IndexCommand

logger = logging.getLogger(__name__)


class Command(IndexCommand):
    """
    TBD
    """
    help = 'Updates the search index to synchronize it with the corresponding data model store.'

    def handle_operation(self, search, queryset):
        logger.info("Indexing {} {} objects".format(queryset.count(), search.model.__name__))
        search.index_qs(queryset)
