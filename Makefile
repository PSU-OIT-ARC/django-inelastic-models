.DEFAULT_GOAL := help
.PHONY = help

SHELL=/bin/bash

python ?= python3.5
venv ?= .env


help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

init:  ## setup a virtualenv
	@if [ "$(python)" == "python2.7" ]; then \
            virtualenv -p $(python) $(venv); \
        else \
            $(python) -m venv $(venv); \
        fi
	$(venv)/bin/pip install .[test]

venv=".env-test"
test: init  ## run tests
	$(venv)/bin/python runtests.py

pypi_release: clean $(venv)  ## update WDT PYPI instance
	$(venv)/bin/python setup.py bdist_wheel --universal
	@for archive in `ls dist`; do \
            scp dist/$${archive} rc.pdx.edu:/tmp/; \
            ssh rc.pdx.edu chgrp arc /tmp/$${archive}; \
            ssh rc.pdx.edu sg arc -c "\"mv /tmp/$${archive} /vol/www/cdn/pypi/dist/\""; \
        done

clean:  ## remove junk
	find . -iname "*.pyc" -or -iname "__pycache__" -delete
	rm -r build | echo "No build artifacts to remove..."
	rm -r dist | echo "No archives to remove..."
