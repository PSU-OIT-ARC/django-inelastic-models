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
def get_handler(sender):
    """
    TBD
    """
    if sender not in get_search_models():
        return None

    handler_path = sender._search_meta().handler
    if handler_path is None:
        return None

    logger.info("Using dependency handler '{}'...".format(handler_path))
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
    if sender is None:
        sender = type(instance)
    if sender not in get_search_models():
        return False

    return True


def should_index(sender, instance):
    """
    TBD
    """
    if sender is None:
        sender = type(instance)
    if sender not in get_search_models():
        return False

    return sender._search_meta().should_index(instance)


def get_dependents(instance):
    """
    TBD
    """
    dependents = {}

    if type(instance) in get_search_models():
        search_meta = type(instance)._search_meta()
        if not search_meta.should_dispatch_dependencies(instance):
            return dependents

    logger.debug("Generating dependents for '{}'".format(instance))
    for model in get_search_models():
        if isinstance(instance, model):
            continue

        search_meta = model._search_meta()
        dependencies = search_meta.get_dependencies()

        for dep_type, select_param in dependencies.items():
            if not isinstance(instance, dep_type):
                continue

            queryset = search_meta.model.objects.filter(**{select_param: instance})
            if (
                    not search_meta.should_index_for_dependency(instance, queryset) or
                    not any([
                        search_meta.should_dispatch_dependencies(_instance)
                        for _instance in queryset.iterator()
                    ])
            ):
                continue

            logger.debug("- Adding '{}' (via {})".format(model, select_param))
            dependents[model] = queryset

    return dependents


@receiver(signals.m2m_changed)
def handle_m2m(sender, **kwargs):
    """
    TBD
    """
    (model_cls, instance, reverse) = (
        kwargs.get('model'), kwargs.get('instance'), kwargs.get('reverse')
    )

    if kwargs['action'] == "pre_clear":
        field = None
        for _field in sender._meta.get_fields():
            if _field.related_model is None:
                continue
            if issubclass(type(instance), _field.related_model):
                field = _field

        objs = []
        if field is not None:
            objs = model_cls.objects.filter(**{field.name: instance.pk})
        if getattr(instance, "_inelasticmodels_m2m_dependents", None) is None:
            instance._inelasticmodels_m2m_dependents = {}

        pk_set = set(objs.values_list('pk', flat=True))
        if instance._inelasticmodels_m2m_dependents.get(model_cls):
            current = instance._inelasticmodels_m2m_dependents[model_cls]
            pk_set = current | pk_set

        instance._inelasticmodels_m2m_dependents = {model_cls: pk_set}

    elif kwargs['action'] == "post_clear":
        logger.debug("M2M dependents of 'clear' on {}".format(instance))
        logger.debug("- {}".format(instance._inelasticmodels_m2m_dependents))

        if reverse:
            dependents = instance._inelasticmodels_m2m_dependents.pop(model_cls)
            for pk in dependents:
                dependent = model_cls.objects.get(pk=pk)
                update_search_index(sender, instance=dependent)
        else:
            update_search_index(sender, instance=instance)

    elif kwargs['action'].startswith("pre_"):
        queryset = model_cls.objects.filter(pk__in=kwargs.get("pk_set"))
        instance._inelasticmodels_m2m_dependents = {
            model_cls: set(queryset.values_list('pk', flat=True))
        }

    elif kwargs['action'].startswith("post_"):
        logger.debug("M2M dependents of 'add/remove' on {}".format(instance))
        logger.debug("- {}".format(instance._inelasticmodels_m2m_dependents))

        if reverse:
            dependents = instance._inelasticmodels_m2m_dependents.pop(model_cls)
            for pk in dependents:
                dependent = model_cls.objects.get(pk=pk)
                update_search_index(sender, instance=dependent)
        else:
            update_search_index(sender, instance=instance)


@receiver(signals.post_delete)
@receiver(signals.post_save)
def update_search_index(sender, **kwargs):
    """
    TBD
    """
    instance = kwargs['instance']
    model_name = str(type(instance)._meta.verbose_name)
    dependents = get_dependents(instance)

    if (
            not is_indexed(sender, instance) or
            is_suspended(sender, instance) or
            not should_index(sender, instance)
    ):
        if not dependents:
            return

        for model, qs in dependents.items():
            dep_name = str(model._meta.verbose_name)

            if not is_indexed(model, None) or is_suspended(model, None):
                logger.debug("Skipping dependency indexing for '{}'".format(dep_name))
                continue

            logger.info("Indexing {} {} records...".format(qs.count(), dep_name))
            for record in qs.iterator():
                update_search_index(model, instance=record)

        return

    logger.debug("Dispatching 'update_search_index' on '{}'".format(instance))

    # Pass 1: Process one-to-{one,many} index dependencies of `instance`
    for model, qs in dependents.items():
        dep_name = str(model._meta.verbose_name)

        if not is_indexed(model, None) or is_suspended(model, None):
            logger.debug("Skipping dependency indexing for '{}'".format(dep_name))
            continue

        logger.info("Indexing {} {} records...".format(qs.count(), dep_name))
        for record in qs.iterator():
            update_search_index(model, instance=record)

    # Pass 2: Process many-to-many index dependencies of `instance`
    m2m_dependents = getattr(instance, '_inelasticmodels_m2m_dependents', {})
    for model, qs in m2m_dependents.items():
        m2m_name = str(model._meta.verbose_name)

        if not is_indexed(model, None) or is_suspended(model, None):
            logger.debug("Skipping dependency indexing for '{}'".format(m2m_name))
            continue

        logger.info("Indexing {} {} records...".format(qs.count(), m2m_name))
        for record in qs.iterator():
            update_search_index(model, instance=record)

    # Pass 3: Process index for `instance`
    handler = get_handler(type(instance))
    if handler is not None:
        logger.info("Indexing '{}' ({})...".format(instance, model_name))
        handler(sender, instance=instance)
    else:
        logger.info("Indexing '{}' ({})...".format(instance, model_name))
        instance.index()


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
