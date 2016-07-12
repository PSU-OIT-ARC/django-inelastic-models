====
TODO
====

1.3
---

* Factor out 'all_field'?
  * Determine if it needs to be defined in 'inelastic_models'.
  * Move it to 'oro.search', if necessary (both the field and it's hooks into indexes).
* Refactor 'inelastic_models.receivers':
  * Keep only actual receiver implementations.
  * Other code/utilities should be moved into 'inelastic_models.utils' (e.g., suspension code paths).
  * 'get_search_models' and 'get_dependents' could probably be moved into 'indexes'.
* General syntax cleanup: code isn't going to win any aesthetic/readability awards.

1.4
---

* ???
