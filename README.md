This is a package that allows indexing of django models using
elasticsearch. It requires django, elasticsearch-py and a local instance of
elasticsearch.

Usage:
------
Add `inelastic_models` to `INSTALLED_APPS`

You must define `ELASTICSEARCH_CONNECTIONS` in your django settings.

Tests:
-----
To run the test suite for Python 2 and Python 3:

    make test

It is assumed you have a `virtualenv` in your path, and Elasticsearch running
on localhost:9200
