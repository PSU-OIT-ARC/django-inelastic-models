from __future__ import unicode_literals
from __future__ import absolute_import

from inelastic_models.management.commands import IndexCommand


class Command(IndexCommand):
    """
    TBD
    """
    help = 'Creates and populates the search index.  If it already exists, it is deleted first.'

    def handle_operation(self, search, queryset):
        print("Creating mapping for %s" % search.model.__name__)
        search.put_mapping()
        print("Indexing %d %s objects" % (
            queryset.count(), search.model.__name__))
        search.index_qs(queryset)
