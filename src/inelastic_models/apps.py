from django.apps import AppConfig

from inelastic_models.utils import autoload_submodules


class SearchConfig(AppConfig):
    name = "inelastic_models"
    verbose_name = "Search"
    default = True

    def ready(self):
        # ensure 'indexes' submodules are loaded
        autoload_submodules(["indexes"])

        # ensure signal handlers are loaded/registered
        from . import receivers
