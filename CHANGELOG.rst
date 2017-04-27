=========
CHANGELOG
=========

1.4
---

* Adds explicit support for translated fields.

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
