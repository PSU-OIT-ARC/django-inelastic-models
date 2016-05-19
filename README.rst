======
README
======

.. image:: https://api.shippable.com/projects/5733d0a22a8192902e1fc666/badge?branch=master

Introduction
------------
This package provides a small library for declaratively specifying indexes for `Django`_ models
using an `Elasticsearch`_ backend.

It requires Django, `elasticsearch-py`_ and an available Elasticsearch instance.

.. _Django: https://docs.djangoproject.org
.. _Elasticsearch: https://www.elastic.co/products/elasticsearch
.. _elasticsearch-py: https://github.com/elastic/elasticsearch-py

Usage
-----

* Add ``inelastic_models`` to ``INSTALLED_APPS``.
* Mixin the type ``inelastic_models.models.SearchMixin`` to your models.
* Implement a type ``inelastic_models.models.Search`` and bind it to models::

    from .models import Foo

    class FooIndex(Search):
        attribute_fields = ('foo', 'baz')

    FooIndex.bind_to_model(Foo)

* You must define ``ELASTICSEARCH_CONNECTIONS``::

    ELASTICSEARCH_CONNECTIONS={
        'default': {
            'HOSTS': ['http://localhost:9200'],
            'INDEX_NAME': 'inelastic_models',
        }
    },


Tests
-----
Use `tox`_ to run the test suite. Run tests independently using ``make``::

    make test [venv=<path>] [python=<python executable name, e.g., 'python3.5'>]

It is assumed that you have ``tox`` and ``virtualenv`` available on your path.

.. _tox: https://testrun.org/tox/latest/
