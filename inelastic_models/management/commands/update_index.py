from __future__ import unicode_literals
from __future__ import absolute_import

from inelastic_models.management.commands import IndexCommand


class Command(IndexCommand):
    """
    TBD
    """
    help = 'Updates the search index to synchronize it with the corresponding data model store.'

    def handle_operation(self, search, queryset):
        print("Indexing %d %s objects" % (
            queryset.count(), search.model.__name__))
        search.index_qs(queryset)
        search.bulk_prune()
