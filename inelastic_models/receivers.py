import functools
import importlib
import logging

from contextlib import contextmanager
from datetime import timedelta

import elasticsearch.exceptions

from django.utils.timezone import now
from django.core.cache import caches
from django.dispatch import receiver
from django.db.models import signals
from django.conf import settings
from django.apps import apps

from .utils import merge
from .indexes import SearchMixin

SUSPENSION_BUFFER_TIME = timedelta(seconds=10)
logger = logging.getLogger(__name__)
suspended_models = []


@functools.lru_cache()
def get_search_models():
    return [m for m in apps.get_models() if issubclass(m, SearchMixin)]


def _is_suspended(model):
    global suspended_models

    for models in suspended_models:
        if model in models:
            return True

    return False


def get_dependents(instance):
    dependents = {}
    for model in get_search_models():
        search_meta = model._search_meta()
        dependencies = search_meta.get_dependencies()
        for dep_type in dependencies:
            if not isinstance(instance, dep_type):
                continue

            filter_kwargs = {dependencies[dep_type]: instance}
            qs = search_meta.model.objects.filter(**filter_kwargs)
            dependents[model] = qs

    return dependents


@receiver(signals.pre_save)
@receiver(signals.pre_delete)
def collect_dependents(sender, **kwargs):
    instance = kwargs['instance']
    instance._search_dependents = get_dependents(instance)


@receiver(signals.post_delete)
@receiver(signals.post_save)
def update_search_index(sender, **kwargs):
    search_models = get_search_models()
    instance = kwargs['instance']

    # Gathering and handling of dependents is performed first in order to support
    # indexed models which list non-indexed models as dependency triggers.
    dependents = merge([instance._search_dependents, get_dependents(instance)])
    handler = getattr(settings, 'ELASTICSEARCH_DEPENDENCY_HANDLER', None)

    for model, qs in dependents.items():
        if handler is not None:
            logger.debug("Using dependency handler '{}' for indexing...".format(handler))
            for record in qs.iterator():
                (handler_module, handler_name) = handler.rsplit(sep='.', maxsplit=1)
                module = importlib.import_module(handler_module)
                func = getattr(module, handler_name)
                func(None, instance=record)
        else:
            search_meta = model._search_meta()
            for record in qs.iterator():
                # !!! TODO !!!
                # Why aren't we using 'record.index()'?
                search_meta.index_instance(record)

    # Guards indexing by validating the given model has been bound to an
    # index type and that this type is not currently suspended.
    if not isinstance(instance, sender):
        sender = type(instance)
    if sender not in search_models or _is_suspended(sender):
        logger.debug("Skipping indexing for '{}'".format(sender))
        return

    logger.debug("Indexing instance '{}'".format(instance))
    instance.index()


@receiver(signals.m2m_changed)
def handle_m2m(sender, **kwargs):
    if kwargs['action'].startswith("pre_"):
        collect_dependents(kwargs['model'], **kwargs)
    else:
        update_search_index(kwargs['model'], **kwargs)


@contextmanager
def suspended_updates(models=None, permanent=False):
    global suspended_models
    
    try:
        search_models = get_search_models()
        if models is None:
            models = search_models
        models = set(models)

        start = now() - SUSPENSION_BUFFER_TIME
        suspended_models.append(models)

        yield

    finally:
        suspended_models.remove(models)

        if permanent is True:
            return
        
        search_models = get_search_models()
        for model in search_models:
            search_meta = model._search_meta()
            if model in models or models.intersection(search_meta.dependencies):
                qs = search_meta.get_qs(since=start)
                search_meta.bulk_index(qs)
