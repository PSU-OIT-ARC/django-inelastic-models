.DEFAULT_GOAL := help
.PHONY = help

SHELL=/bin/bash

python ?= python3
venv ?= .env

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

clean:  ## remove junk
	find . -iname "*.pyc" -delete
	rm -r build || echo "No build artifacts to remove..."
	rm -r dist || echo "No archives to remove..."

build-containers: init  ## buidls required containers
	docker pull python:3.6
	$(venv)/bin/docker-compose build test

spawn-containers: init  ## launches required containers
	$(venv)/bin/docker-compose pull
	$(venv)/bin/docker-compose up -d elasticsearch
	@echo "Waiting for containers to start..."
	@sleep 5

test: init spawn-containers  ## run tests
	ELASTICSEARCH_HOST="http://127.0.0.1:9200" $(venv)/bin/python runtests.py

test_container: init build-containers spawn-containers  ## run tests in container
	$(venv)/bin/docker-compose run -u `id -u` --rm test

upload-dist: clean init ## Builds and uploads distribution
	curl -XGET https://packages.wdt.pdx.edu/publish.sh | VENV=$(venv) bash -
