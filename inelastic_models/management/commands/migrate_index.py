from __future__ import unicode_literals
from __future__ import absolute_import

from inelastic_models.management.commands import IndexCommand


class Command(IndexCommand):
    """
    TBD
    """
    help = 'Updates the index mapping, if necessary. This operation destroys the existing index.'

    def handle_operation(self, search, queryset):
        if search.check_mapping():
            print("Mapping '{}' does not require migration.".format(search))
            return

        print("Migrating new or existing mapping '{}'...".format(search))
        search.put_mapping()
        print("(Re-)Indexing mapping '{}'...".format(search))
        search.index_qs(queryset)
