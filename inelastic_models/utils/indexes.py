from __future__ import unicode_literals
from __future__ import absolute_import

import logging

from elasticsearch import Elasticsearch
from django.conf import settings
from ..receivers import get_search_models

logger = logging.getLogger(__name__)


def refresh_search_indexes():
    for name, connection in list(settings.ELASTICSEARCH_CONNECTIONS.items()):
        try:
            es = Elasticsearch(connection['HOSTS'])
            for model in get_search_models():
                search = model._search_meta()
                index = search.get_index()
                logger.debug("Refreshing index '{}'".format(index))
                es.indices.refresh(index=index)
        except Exception as exc:
            logger.error("Error in 'refresh_search_indexes': {0!s}".format(exc))

def clear_search_indexes():
    for name, connection in list(settings.ELASTICSEARCH_CONNECTIONS.items()):
        try:
            es = Elasticsearch(connection['HOSTS'])
            for model in get_search_models():
                search = model._search_meta()
                index = search.get_index()
                logger.debug("Clearing index '{}'".format(index))
                search.bulk_clear()
        except Exception as exc:
            logger.error("Error in 'clear_search_indexes': {0!s}".format(exc))
