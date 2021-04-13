import logging

from inelastic_models.management.commands import IndexCommand

logger = logging.getLogger(__name__)


class Command(IndexCommand):
    """
    TBD
    """
    help = 'Creates and populates the search index.  If it already exists, it is deleted first.'

    def handle_operation(self, search, queryset):
        logger.info("Creating mapping for {}".format(search.model.__name__))
        search.put_mapping()

        logger.info("Indexing {} {} objects".format(queryset.count(), search.model.__name__))
        search.index_qs(queryset)
