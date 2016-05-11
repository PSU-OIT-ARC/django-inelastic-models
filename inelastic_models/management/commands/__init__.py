from __future__ import unicode_literals
from __future__ import absolute_import

from datetime import datetime, timedelta
import six
import re

from django.core.management.base import BaseCommand, CommandError
from inelastic_models.receivers import get_search_models

DURATION_RE = re.compile(
    r"^(?:(?P<days>\d+)D)?"
    r"(?:(?P<hours>\d+)H)?"
    r"(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+)S)?$",
    flags=re.IGNORECASE)


class IndexCommand(BaseCommand):
    help = 'Creates and populates the search index.  If it already exists, it is deleted first.'

    def add_arguments(self, parser):
        parser.add_argument('args', nargs='*', type=six.text_type)
        parser.add_argument('--since', action="store", default='', dest='since',
                            help='Index data updated after this time.  yyyy-mm-dd[-hh:mm] or [#d][#h][#m][#s]')
        parser.add_argument('--limit', action="store", default='', dest='limit',
                            help='Index at most this many of each model.')

    def parse_date_time(self, timestamp):
        try:
            return datetime.strptime(timestamp, "%Y-%m-%d-%H:%M")
        except ValueError:
            pass

        try:
            return datetime.strptime(timestamp, "%Y-%m-%d")
        except ValueError:
            pass

        match = DURATION_RE.match(timestamp)
        if match:
            kwargs = dict((k, int(v)) for (k, v) in list(match.groupdict().items()) if v is not None)
            return datetime.now() - timedelta(**kwargs)

        raise ValueError("%s could not be interpereted as a datetime" % timestamp)

    def get_models(self, args):
        models = get_search_models()
        if args:
            models = [m for m in models if
                      m._meta.app_label in args or
                      '%s.%s' % (m._meta.app_label, m._meta.model_name) in args]

        return models

    def handle(self, *args, **options):
        models = self.get_models(args)
        if not models:
            raise CommandError("No matching indices found.")

        since = None
        if options['since']:
            since = self.parse_date_time(options['since'])

        limit = None
        if options['limit']:
            limit = int(options['limit'])

        for model in models:
            search = model._search_meta()
            queryset = search.get_qs(since=since, limit=limit)
            self.handle_operation(search, queryset)

    def handle_operation(self, search, queryset):
        raise NotImplementedError
