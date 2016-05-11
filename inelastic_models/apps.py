from django.apps import AppConfig

from inelastic_models.utils import autoload_submodules


class SearchConfig(AppConfig):
    name = 'inelastic_models'
    verbose_name = "Search"

    def ready(self):
        autoload_submodules(['indexes'])
        from . import receivers
