"""Declarative Elasticsearch indexes for Django models."""

from importlib.metadata import version, PackageNotFoundError


try:
    __version__ = version("django-inelastic-models")
except PackageNotFoundError:
    # package is not installed
    pass


__all__ = ["__version__"]
