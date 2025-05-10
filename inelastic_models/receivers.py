import collections
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
def get_signal_name(signal):
    """
    TBD
    """
    if signal == signals.post_save:
        return "update"
    elif signal == signals.post_delete:
        return "delete"
    elif signal == signals.m2m_changed:
        return "m2m_changed"

    return "unknown"


@functools.lru_cache()
def get_search_models():
    """
    TBD
    """
    return [m for m in apps.get_models() if issubclass(m, SearchMixin)]


@functools.lru_cache
def get_reverse_dependencies():
    """
    TBD
    """
    reverse_dependencies = collections.defaultdict(list)

    for model in get_search_models():
        dependencies = model._search_meta().get_dependencies()
        if not dependencies:
            continue

        for dep_type, select_param in dependencies.items():
            reverse_dependencies[dep_type].append((model, select_param))

    return reverse_dependencies


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
    (handler_module, handler_name) = handler_path.rsplit(sep=".", maxsplit=1)
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
    reverse_dependencies = get_reverse_dependencies()
    dependents = {}

    if (
        not is_indexed(type(instance), None)
        and type(instance) not in reverse_dependencies
    ):
        logger.debug("Skipping non-depended type '{}'".format(type(instance)))
        return dependents

    for model_type in list(instance._meta.parents.keys()) + [instance._meta.model]:
        for model, select_param in reverse_dependencies[model_type]:
            search_meta = model._search_meta()
            queryset = search_meta.get_base_qs().filter(**{select_param: instance})
            if not search_meta.should_index_for_dependency(instance, queryset):
                continue

            pk_set = set()
            for _instance in queryset.iterator():
                if search_meta.should_dispatch_dependencies(_instance):
                    pk_set.add(_instance.pk)

            logger.debug(
                "- Adding {} '{}' (via {})".format(
                    len(pk_set), model._meta.verbose_name, select_param
                )
            )
            dependents[model] = pk_set

    return dependents


def process_update(sender, **kwargs):
    """
    TBD
    """
    (instance, signal) = (kwargs.pop("instance"), kwargs.pop("signal", None))
    model_name = str(instance._meta.verbose_name)

    logger.debug("Dispatching 'process_update' on '{}'".format(instance))

    # Process index dependencies of `instance`
    for model, pk_set in get_dependents(instance).items():
        dep_name = str(model._meta.verbose_name)

        if not is_indexed(model, None) or is_suspended(model, None):
            logger.debug("Skipping dependency indexing for '{}'".format(dep_name))
            continue

        logger.debug(
            "Dispatching update of {} {} records...".format(len(pk_set), dep_name)
        )
        queryset = model._search_meta().get_base_qs()
        for record in queryset.filter(pk__in=pk_set).iterator():
            process_update(model, instance=record)

    if (
        not is_indexed(sender, instance)
        or is_suspended(sender, instance)
        or (
            signal != signals.post_delete
            and not should_index(sender, instance)
        )
    ):
        return

    # Process index for `instance`
    instance.index()


@receiver(signals.m2m_changed)
def handle_m2m(sender, **kwargs):
    """
    TBD
    """
    (model_cls, instance, m2m_action, reverse) = (
        kwargs.get("model"),
        kwargs.get("instance"),
        kwargs.get("action"),
        kwargs.get("reverse"),
    )

    if m2m_action == "pre_clear":
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

        pk_set = set(objs.values_list("pk", flat=True))
        if instance._inelasticmodels_m2m_dependents.get(model_cls):
            current = instance._inelasticmodels_m2m_dependents[model_cls]
            pk_set = current | pk_set

        instance._inelasticmodels_m2m_dependents = {model_cls: pk_set}

    elif m2m_action.startswith("pre_"):
        queryset = model_cls.objects.filter(pk__in=kwargs.get("pk_set"))

        # stores related objects to be handled by post_save on instance
        # as well as post_{add,remove} on the m2m relation in the case that
        # this codepath is not within a pre_save/post_save transaction on
        # the record given by instance.
        instance._inelasticmodels_m2m_dependents = {
            model_cls: set(queryset.values_list("pk", flat=True))
        }

    elif m2m_action.startswith("post_"):
        logger.debug("M2M dependents of '{}' on {}".format(m2m_action, instance))
        logger.debug("- {}".format(instance._inelasticmodels_m2m_dependents))

        for model, pk_set in instance._inelasticmodels_m2m_dependents.items():
            m2m_name = str(model._meta.verbose_name)

            if not is_indexed(model, None) or is_suspended(model, None):
                logger.debug("Skipping dispatch of update for '{}'".format(m2m_name))
                continue

            logger.debug(
                "Dispatching update of {} {} records...".format(len(pk_set), m2m_name)
            )
            queryset = model._search_meta().get_base_qs()
            for record in queryset.filter(pk__in=pk_set).iterator():
                logger.debug(
                    "Dispatching update of {} {}...".format(record, record._meta.model)
                )
                handle_instance(
                    record._meta.model,
                    instance=record,
                    signal=kwargs["signal"]
                )

        parent_model = instance._meta.model
        parent_name = str(instance._meta.verbose_name)

        if not is_indexed(parent_model, None) or is_suspended(parent_model, None):
            logger.debug("Skipping dispatch of update for '{}'".format(parent_name))
            return

        logger.debug(
            "Dispatching update of {} record {}...".format(parent_name, instance)
        )
        handle_instance(parent_model, instance=instance, signal=kwargs["signal"])


@receiver(signals.post_save)
@receiver(signals.post_delete)
def handle_instance(sender, **kwargs):
    """
    TBD
    """
    (instance, signal) = (kwargs["instance"], kwargs["signal"])
    model_name = str(instance._meta.verbose_name)
    handler = get_handler(type(instance))

    if handler is not None:
        logger.debug(
            "Dispatching index update for '{}' ({}) via {}...".format(
                instance, model_name, get_signal_name(signal)
            )
        )

        handler(sender, **kwargs)

    else:
        logger.debug(
            "Processing index update for '{}' ({}) via {}...".format(
                instance, model_name, get_signal_name(signal)
            )
        )

        process_update(sender, **kwargs)


@contextmanager
def suspended_updates(models=None, permanent=False, slop=timedelta(seconds=10)):
    """
    TBD
    """
    global SUSPENDED_MODELS

    try:
        search_models = get_search_models()
        reverse_dependencies = get_reverse_dependencies()

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

        for model in models:
            if is_indexed(model, None):
                search_meta = model._search_meta()
                queryset = search_meta.get_qs(since=start)
                search_meta.bulk_index(queryset)
            for dependency, select_param in reverse_dependencies[model]:
                search_meta = dependency._search_meta()
                queryset = search_meta.get_qs(since=start)
                search_meta.bulk_index(queryset)
