.DEFAULT_GOAL := help
.PHONY = help

SHELL=/bin/bash

python ?= python3
venv ?= .env

remote_user ?= `whoami`
remote_host="$(remote_user)@rc.pdx.edu"


help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

init:  ## setup a virtualenv
	@if [ "$(python)" == "python2.7" ]; then \
            virtualenv -p $(python) $(venv); \
        else \
            $(python) -m venv $(venv); \
        fi
	$(venv)/bin/pip install wheel
	$(venv)/bin/pip install .[test]

pypi_release: clean init ## update WDT PYPI instance
	echo "Using remote_host: $(remote_host)"
	$(venv)/bin/python setup.py bdist_wheel --universal
	@for archive in `ls dist`; do \
            scp dist/$${archive} $(remote_host):/tmp/; \
            ssh $(remote_host) chgrp arc /tmp/$${archive}; \
            ssh $(remote_host) sg arc -c "\"mv /tmp/$${archive} /vol/www/cdn/pypi/dist/\""; \
        done

clean:  ## remove junk
	find . -iname "*.pyc" -delete
	rm -r build || echo "No build artifacts to remove..."
	rm -r dist || echo "No archives to remove..."

venv=".env-test"
test: init  ## run tests
	$(venv)/bin/python runtests.py
