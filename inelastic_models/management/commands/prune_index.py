import logging

from inelastic_models.management.commands import IndexCommand

logger = logging.getLogger(__name__)


class Command(IndexCommand):
    """
    TBD
    """
    help = 'Prunes the search index to synchronize it with the corresponding data model store.'

    def handle_operation(self, search, queryset):
        logger.info("Pruning {} objects".format(search.model.__name__))
        search.bulk_prune()
