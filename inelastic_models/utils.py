from __future__ import unicode_literals
from __future__ import absolute_import

import importlib
import logging

from elasticsearch import Elasticsearch

from django.utils.module_loading import module_has_submodule
from django.core.paginator import Paginator, Page
from django.conf import settings
from django.apps import apps

from inelastic_models.receivers import get_search_models


logger = logging.getLogger(__name__)


class SearchPaginator(Paginator):
    def _get_page(self, *args, **kwargs):
        return SearchPage(*args, **kwargs)

class SearchPage(Page):
    def __len__(self):
        return self.object_list._extra['size']

def autoload_submodules(submodules):
    """
    Autoload the given submodules for all apps in INSTALLED_APPS.

    This utility was inspired by 'admin.autodiscover'.
    """
    for app in apps.get_app_configs():
        logger.debug("Analyzing app '%s' for modules '%s'" % (app, submodules))
        for submodule in submodules:
            dotted_path = "{0}.{1}".format(app.name, submodule)
            try:
                importlib.import_module(dotted_path)
            except:
                if module_has_submodule(app.module, submodule):
                    msg = "Trouble importing module '%s'"
                    logger.warn(msg % (dotted_path))
                    raise
            else:
                logger.debug("Imported module '%s'" % (dotted_path))

def refresh_search_indexes():
    for name, connection in list(settings.ELASTICSEARCH_CONNECTIONS.items()):
        try:
            es = Elasticsearch(connection['HOSTS'])
            for model in get_search_models():
                index = model._search_meta().get_index()
                logger.debug("Refreshing index '{}'".format(index))
                es.indices.refresh(index=index)
                es.indices.flush(wait_if_ongoing=True)
        except Exception as exc:
            logger.error("Error in 'refresh_search_indexes': {0!s}".format(exc))

def clear_search_indexes():
    for name, connection in list(settings.ELASTICSEARCH_CONNECTIONS.items()):
        try:
            es = Elasticsearch(connection['HOSTS'])
            for model in get_search_models():
                index = model._search_meta().get_index()
                logger.debug("Clearing index '{}'".format(index))
                es.indices.delete(index=index)
                es.indices.create(index=index)
                es.indices.flush(wait_if_ongoing=True)
        except Exception as exc:
            logger.error("Error in 'clear_search_indexes': {0!s}".format(exc))
