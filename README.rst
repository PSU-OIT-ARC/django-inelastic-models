======
README
======

.. image:: https://api.shippable.com/projects/5733d0a22a8192902e1fc666/badge?branch=master

Introduction
------------
This package provides a small library for declaratively specifying indexes for `Django`_ models
using an `Elasticsearch`_ backend.

It requires Django, `elasticsearch-dsl`_ and an available Elasticsearch instance.

.. _Django: https://docs.djangoproject.org
.. _Elasticsearch: https://www.elastic.co/products/elasticsearch
.. _elasticsearch-dsl: https://github.com/elastic/elasticsearch-dsl-py

Usage
-----

1. Add ``inelastic_models`` to ``INSTALLED_APPS``.
2. Mixin the type ``inelastic_models.indexes.SearchMixin`` to your models.
3. Implement a type ``inelastic_models.indexes.Search`` and bind it to models::

    from .models import Foo

    class FooIndex(Search):
        attribute_fields = ('foo', 'baz')

    FooIndex.bind_to_model(Foo)

You must define ``ELASTICSEARCH_CONNECTIONS``. Pass connection parameters to the
underlying ``Elasticsearch`` instance via the ``CONNECTION_OPTIONS`` mapping::

    ELASTICSEARCH_CONNECTIONS = {
        'default': {
            'HOSTS': ['http://localhost:9200'],
            'INDEX_NAME': 'inelastic_models',
	    'CONNECTION_OPTIONS': {
	        'timeout': 42,
		'retry_on_timeout': True
	    }
        }
    },

Tests
-----
Use `tox`_ to run the test suite. Run tests independently using ``make``::

    make test [venv=<path>] [python=<python executable name, e.g., 'python3.5'>]

It is assumed that you have ``tox`` and ``virtualenv`` available on your path.

.. _tox: https://testrun.org/tox/latest/
