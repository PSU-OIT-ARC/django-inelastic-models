import functools
import importlib
import logging

from contextlib import contextmanager
from datetime import timedelta

from django.utils.timezone import now
from django.dispatch import receiver
from django.db.models import signals
from django.conf import settings
from django.apps import apps

from .indexes import SearchMixin
from .utils import merge

SUSPENDED_MODELS = []

logger = logging.getLogger(__name__)


@functools.lru_cache()
def get_search_models():
    """
    TBD
    """
    return [
        m for m in apps.get_models()
        if issubclass(m, SearchMixin)
    ]


@functools.lru_cache()
def get_handler():
    """
    TBD
    """
    handler_path = getattr(settings, 'ELASTICSEARCH_INDEX_HANDLER', None)
    if handler_path is None:
        return None

    logger.debug("Using dependency handler '{}'...".format(handler_path))
    (handler_module, handler_name) = handler.rsplit(sep='.', maxsplit=1)
    module = importlib.import_module(handler_module)
    return getattr(module, handler_name)


def get_dependents(instance):
    """
    TBD
    """
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


def is_suspended(sender, instance):
    """
    TBD
    """
    global SUSPENDED_MODELS

    if sender is None or not isinstance(instance, sender):
        sender = type(instance)
    for models in SUSPENDED_MODELS:
        if sender in models:
            return True

    return False


def is_indexed(sender, instance):
    """
    TBD
    """
    search_models = get_search_models()

    if sender is None or not isinstance(instance, sender):
        sender = type(instance)
    if sender not in search_models:
        return False

    return True


@receiver(signals.pre_save)
@receiver(signals.pre_delete)
def collect_dependents(sender, **kwargs):
    """
    TBD
    """
    instance = kwargs['instance']

    # Guards indexing by validating the given model has been bound to an
    # index type and that this type is not currently suspended.
    if not is_indexed(sender, instance) or is_suspended(sender, instance):
        logger.debug("Skipping pre-indexing task for '{}'".format(sender))
        return

    instance._search_dependents = get_dependents(instance)


@receiver(signals.post_delete)
@receiver(signals.post_save)
def update_search_index(sender, **kwargs):
    """
    TBD
    """
    instance = kwargs['instance']
    handler = get_handler()

    for model, qs in instance._dependents.items():
        # Guards indexing by validating the given model has been bound to an
        # index type and that this type is not currently suspended.
        if not is_indexed(model, None) or is_suspended(model, None):
            logger.debug("Skipping dependency indexing for '{}'".format(model))
            continue

        if handler is not None:
            for record in qs.iterator():
                handler(None, instance=record)
        else:
            search_meta = model._search_meta()
            for record in qs.iterator():
                instance.index()

    # Guards indexing by validating the given model has been bound to an
    # index type and that this type is not currently suspended.
    if not is_indexed(sender, instance) or is_suspended(sender, instance):
        logger.debug("Skipping indexing for '{}' ({})".format(instance, model))
        return

    if handler is not None:
        handler(sender, instance=instance)
    else:
        instance.index()


@receiver(signals.m2m_changed)
def handle_m2m(sender, **kwargs):
    """
    TBD
    """
    if kwargs['action'].startswith("pre_"):
        collect_dependents(kwargs['model'], **kwargs)
    else:
        update_search_index(kwargs['model'], **kwargs)


@contextmanager
def suspended_updates(models=None, permanent=False, slop=timedelta(seconds=10)):
    """
    TBD
    """
    global SUSPENDED_MODELS
    
    try:
        search_models = get_search_models()
        if models is None:
            models = search_models
        models = set(models)

        start = now() - slop
        SUSPENDED_MODELS.append(models)

        yield

    finally:
        SUSPENDED_MODELS.remove(models)

        if permanent is True:
            return
        
        search_models = get_search_models()
        for model in search_models:
            search_meta = model._search_meta()
            if model in models or models.intersection(search_meta.dependencies):
                qs = search_meta.get_qs(since=start)
                search_meta.bulk_index(qs)
