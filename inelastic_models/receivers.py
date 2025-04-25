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
        logger.warning("handler_path is None:  {}...".format(handler_path))
        return None

    logger.debug("Using dependency handler '{}'...".format(handler_path))
    (handler_module, handler_name) = handler_path.rsplit(sep='.', maxsplit=1)
    module = importlib.import_module(handler_module)
    return getattr(module, handler_name)


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

    if sender is None:
        sender = type(instance)
    if sender not in search_models:
        return False

    return True


def get_dependents(instance):
    """
    TBD
    """
    dependents = {}

    if type(instance) in get_search_models():
        search_meta = type(instance)._search_meta()
        if not search_meta.should_dispatch_dependencies(instance):
            return dependents

    for model in get_search_models():
        search_meta = model._search_meta()
        dependencies = search_meta.get_dependencies()

        for dep_type, select_param in dependencies.items():
            if not isinstance(instance, dep_type):
                continue

            filter_kwargs = {select_param: instance}
            queryset = search_meta.model.objects.filter(**filter_kwargs)
            if queryset.exists():
                dependents[model] = queryset

    return dependents


@receiver(signals.m2m_changed)
def handle_m2m(sender, **kwargs):
    """
    TBD
    """
    if kwargs['action'].startswith("pre_"):
        (model_cls, instance) = (kwargs.get('model'), kwargs.get('instance'))
        instance._inelasticmodels_m2m_dependents = {
            model_cls: model_cls.objects.filter(pk__in=kwargs.get("pk_set"))
        }


@receiver(signals.post_delete)
@receiver(signals.post_save)
def update_search_index(sender, **kwargs):
    """
    TBD
    """
    instance = kwargs['instance']
    handler = get_handler()

    # Pass 1: Process one-to-{one,many} index dependencies of `instance`
    for model, qs in get_dependents(instance).items():
        if not is_indexed(model, None) or is_suspended(model, None):
            logger.debug("Skipping dependency indexing for '{}'".format(model))
            continue

        logger.info(
            "Indexing {} {} records...".format(
                qs.count(), str(model._meta.verbose_name)
            )
        )

        if handler is not None:
            for record in qs.iterator():
                logger.debug("Indexing '{}' ({})...".format(record, type(record)))
                handler(None, instance=record)
        else:
            search_meta = model._search_meta()
            for record in qs.iterator():
                logger.debug("Indexing '{}' ({})...".format(record, type(record)))
                record.index()

    # Pass 2: Process index for `instance`
    if not is_indexed(sender, instance) or is_suspended(sender, instance):
        logger.debug("Skipping indexing for '{}' ({})".format(instance, sender))
        return

    if handler is not None:
        logger.debug("Indexing '{}' ({})...".format(instance, sender))
        handler(sender, instance=instance)
    else:
        logger.debug("Indexing '{}' ({})...".format(instance, sender))
        instance.index()

    # Pass 3: Process many-to-many index dependencies of `instance`
    m2m_dependents = getattr(instance, '_inelasticmodels_m2m_dependents', {})
    for model, qs in m2m_dependents.items():
        if not is_indexed(model, None) or is_suspended(model, None):
            logger.debug("Skipping dependency indexing for '{}'".format(model))
            continue

        logger.info(
            "Indexing {} {} records...".format(
                qs.count(), str(model._meta.verbose_name)
            )
        )

        if handler is not None:
            for record in qs.iterator():
                logger.debug("Indexing '{}' ({})...".format(record, type(record)))
                handler(None, instance=record)
        else:
            search_meta = model._search_meta()
            for record in qs.iterator():
                logger.debug("Indexing '{}' ({})...".format(record, type(record)))
                record.index()


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
