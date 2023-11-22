=========
Changelog
=========

8.0
---

2023-11-22

This release adds support for, and requires, the use of ES 8.x.

7.1
---

2022-06-08

This release requires the use of the Django 3.2 LTS.

7.0
---

2021-11-23

This release adds support for, and requires, the use of ES 7.x.

This release marks a departure from the previous release strategy.
To reduce confusion and to provide better support for a variety of
Elasticsearch installations, releases will follow the major ES
release versions as is done with the 'elasticsearch-py' and the
'elasticsearch-dsl-py' packages.

* Uses analyzer, tokenizer constructions compatible with ES >= 5.0
* Replaces the use of the 'string' type field with 'text' [ES>=5.0].
* Removes use of 'flush' API [ES>=6].
* Removes support for Python 2 and related compatibility shims.
* Replaces deprecated ngram type names [ES>=8.0].
* Revises index construction to support mapping type removal [ES>=8.0].
* Adds new field 'KitchenSinkField' to replace the functionality
  of the historical '_all' index field [ES>=6.0].

1.5
---

2020-02-27

* Fixes exception handling during chunked indexing.
* Improves performance of 'bulk_prune' operation.
* Fixes erroneous dict modification during iteration.
* Adds missing assertions, guards for empty index requests.
* Adds support for WDT PYPI instance.

1.4
---

* Adds explicit support for translated fields.
* Replaces uses of print function.
* Uses memory-efficient record iteration for bulk operations.

1.3
---

* Adds support for connection parameter configuration via 'ELASTICSEARCH_CONNECTIONS'.

1.2
---

* Enforces a one-to-one relation between Elasticsearch indices and mappings in order to
  simplify implementation and behavior.
* Retargets to the Elasticsearch 2.x release series.
* Revises incorrect test case specifications.
* Adds new index API 'Search.check_mapping'.
* Adds new management command 'migrate_index'.

1.1
---

Adds explicit index-binding.

1.0
---

The initial pre-release which serves to replicate 'oro.search' as an external package.
