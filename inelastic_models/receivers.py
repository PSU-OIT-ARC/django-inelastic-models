import threading
import logging

from contextlib import contextmanager
from datetime import timedelta

import elasticsearch.exceptions

from django.utils.lru_cache import lru_cache
from django.utils.timezone import now
from django.core.cache import caches
from django.dispatch import receiver
from django.db.models import signals
from django.apps import apps

from .utils import merge
from .indexes import SearchMixin

SUSPENSION_BUFFER_TIME = timedelta(seconds=10)
logger = logging.getLogger(__name__)
suspended_models = []


@lru_cache()
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

    if not isinstance(instance, sender):
        sender = type(instance)
    if sender not in search_models or _is_suspended(sender):
        logger.debug("Skipping indexing for '%s'" % (sender))
        return

    instance.index()
    
    dependents = merge([instance._search_dependents, get_dependents(instance)])
    for model, qs in dependents.items():
        search_meta = model._search_meta()
        for record in qs.iterator():
            search_meta.index_instance(record)


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
