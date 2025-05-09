============
Introduction
============

This package provides a small library for declaratively specifying indexes for
`Django`_ models using an `Elasticsearch`_ backend.

It requires Django, `elasticsearch-dsl`_ and an available Elasticsearch instance.

.. _Django: https://docs.djangoproject.org
.. _Elasticsearch: https://www.elastic.co/products/elasticsearch
.. _elasticsearch-dsl: https://github.com/elastic/elasticsearch-dsl-py

Compatibility
-------------

The following compatibility matrix summarizes supported versions of the
`Elasticsearch` engine.

+------+--------+--------+-------------+-------------+--------+-------------+
|      | ES 1.X | ES 2.X | ES 5.X      | ES 6.X      | ES 7.X | ES 8.X      |
+======+========+========+=============+=============+========+=============+
| 1.0  |   Y    |   N    |   N         |    N        |   N    |   N         |
+------+--------+--------+-------------+-------------+--------+-------------+
| 1.1  |   Y    |   N    |   N         |    N        |   N    |   N         |
+------+--------+--------+-------------+-------------+--------+-------------+
| 1.2  |   N    |   Y    |   N         |    N        |   N    |   N         |
+------+--------+--------+-------------+-------------+--------+-------------+
| 7.0  |   N    |   N    |   ? [#f1]_  |    ? [#f1]_ |   Y    |   ? [#f1]_  |
+------+--------+--------+-------------+-------------+--------+-------------+
| 8.0  |   N    |   N    |   N         |    N        |   N    |   Y         |
+------+--------+--------+-------------+-------------+--------+-------------+

.. [#f1] Compatibilty is possible but not officially supported.

Releases prior to 7.0 unofficially supported a variety of Django release
series and did not explicitly indicate supported combinations. No official
support or guidance is given for these releases.

+------+------------+------------+
|      | Django 3.2 | Django 4.2 |
+======+============+============+
| 7.0  |      Y     |      N     |
+------+------------+------------+
| 8.0  |      Y     |  planned   |
+------+------------+------------+

Usage
-----

1. Add ``inelastic_models`` to ``INSTALLED_APPS``.
2. Mixin the type ``inelastic_models.indexes.SearchMixin`` to your models.
3. Implement a type ``inelastic_models.indexes.Search`` and bind it to models::

    from .models import Foo

    class FooIndex(Search):
        attribute_fields = ('foo', 'baz')

    FooIndex.bind_to_model(Foo)

You must define ``ELASTICSEARCH_CONNECTIONS``. Pass index and connection parameters
to the generated indices and the underlying ``Elasticsearch`` instance via the
``INDEX_OPTIONS`` and ``CONNECTION_OPTIONS`` mappings, respectively::

    ELASTICSEARCH_CONNECTIONS = {
        'default': {
            'HOSTS': ['http://localhost:9200'],
            'INDEX_NAME': 'inelastic_models',
	    'INDEX_OPTIONS': {
	        'number_of_replicas': 3
	    },
	    'CONNECTION_OPTIONS': {
	        'timeout': 42,
		'retry_on_timeout': True
	    }
        }
    },

Tests
-----
Run tests using the ``make`` rule::

    make test [venv=<path>] [python=<python executable name, e.g., 'python3.5'>]

It is assumed that you have and Elasticsearch index available at ``elasticsearch:9200`` and that
``virtualenv`` available on your path.
