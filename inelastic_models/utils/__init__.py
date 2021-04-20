from itertools import chain
import importlib
import logging

from django.utils.module_loading import module_has_submodule
from django.apps import apps

logger = logging.getLogger(__name__)


def merge(items, overwrite=True):
    if not items:
        return {}

    if len(items) == 1:
        return items[0]

    if all(isinstance(i, dict) for i in items):
        # Merge dictionaries by recursively merging each key.
        keys = set(chain.from_iterable(i.keys() for i in items))
        return dict((k, merge([i[k] for i in items if k in i], overwrite)) for k in keys)
    elif all(isinstance(i, list) for i in items):
        # Merge lists by chaining them together.
        return list(set(chain.from_iterable(items)))
    elif all(isinstance(i, set) for i in items):
        # Merge sets by unioning them together.
        return set().union(*items)
    else:
        if overwrite:
            # Merge other values by selecting the last one.
            return items[-1]
        raise ValueError("Collision while merging. Values: %s" % items)


def autoload_submodules(submodules):
    """
    Autoload the given submodules for all apps in INSTALLED_APPS.

    This utility was inspired by 'admin.autodiscover'.
    """
    for app in apps.get_app_configs():
        logger.debug("Analyzing app '{}' for modules '{}'".format(app, submodules))
        for submodule in submodules:
            dotted_path = "{0}.{1}".format(app.name, submodule)
            try:
                importlib.import_module(dotted_path)
            except:
                if module_has_submodule(app.module, submodule):
                    msg = "Trouble importing module '{}'"
                    logger.warn(msg.format(dotted_path))
                    raise
            else:
                logger.debug("Imported module '{}'".format(dotted_path))
