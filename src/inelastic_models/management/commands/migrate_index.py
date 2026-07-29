import logging

from inelastic_models.management.commands import IndexCommand

logger = logging.getLogger(__name__)


class Command(IndexCommand):
    """
    TBD
    """

    help = "Updates the index mapping, if necessary. This operation destroys the existing index."

    def handle_operation(self, search, queryset):
        index = search.get_index()
        if search.check_mapping():
            logger.info("Mapping '{}' does not require migration.".format(index))
            return

        logger.info("Migrating new or existing mapping '{}'...".format(index))
        search.put_mapping()

        logger.info("(Re-)Indexing mapping '{}'...".format(index))
        search.bulk_index(queryset)
