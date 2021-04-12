.DEFAULT_GOAL = help

venv ?= .env
venv_python ?= python3
venv_update = false

bin = $(venv)/bin
docker-compose = "`which docker-compose`"

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

init:  ## Install primary application dependencies, creating a virtualenv if necessary. Params: 'venv', 'venv_python', 'venv_autoinstall', 'venv_requirements', 'venv_update'
	@if [ -d "$(venv)" ]; then \
            echo "virtualenv '$(venv)' exists"; \
            if [ $(venv_update) = true ]; then \
                $(bin)/pip install --upgrade pip wheel; \
                $(bin)/pip install .[test]; \
            fi \
        else \
            $(venv_python) -m venv $(venv) || exit -1; \
            $(bin)/pip install --upgrade pip wheel; \
            $(bin)/pip install .[test]; \
        fi

#test: venv_update=true
test: init  ## Run tests
	$(venv)/bin/python runtests.py

test-container: init  ## Run tests in a container
	$(docker-compose) up -d elasticsearch
	$(docker-compose) build test
	$(docker-compose) run test make test venv=.env-test
	# sudo rm -rf .env-test

upload-dist: clean init ## Builds and uploads distribution
	curl -XGET https://packages.wdt.pdx.edu/publish.sh | VENV=$(venv) bash -

clean:  ## Removes generated junk
	@rm -r build || echo "No build artifacts to remove..."
	@rm -r dist || echo "No archives to remove..."
	@rm -r *.egg-info || echo "No eggs to remove..."
