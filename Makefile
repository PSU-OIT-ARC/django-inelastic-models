.DEFAULT_GOAL := help
.PHONY := help update_requirements documentation update_formatting static_analysis release test upload-dist

SHELL=/bin/bash
APP_ENV ?= ""

pipenv_python ?= python3.11
pipenv_bin = "`pipenv --venv`/bin"
ifneq ($(APP_ENV), "")
  pipenv_bin = "$(APP_ENV)/bin"
endif

package_path = "src/inelastic_models"
package_venv = ".venv-pkg"
package_optionals = ""

ruff_target_python = "py311"


help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

update_requirements:  ## Updates project dependencies
	@echo "Updating Python release requirements..."; echo ""
	@pipenv --venv || pipenv --python $(pipenv_python)
	@pipenv update --dev
	@pipenv update --outdated || echo "Review the above outdated packages..."
	@pipenv verify || (echo "Verification failed!" && exit 1)
	@pipenv clean

documentation:  ## Builds the currently available documentation.
	@cp README.rst docs/source/introduction.rst
	@cp CHANGELOG.rst docs/source/changelog.rst
	@pipenv run sphinx-build -b html docs/source docs/
	@pipenv run sphinx-build -b latex docs/source docs/build;
	@cd docs/build; make all; cp inelastic_models.pdf ../assets/; cd ../../

update_formatting:  ## Reformats source code given by path. Params: 'target_path'
	@echo "Formatting source tree ..."
	@pipenv run ruff format --target-version $(ruff_target_python) *.py
	@pipenv run ruff format --target-version $(ruff_target_python) $(package_path)

static_analysis:  ## Performs static analysis of source tree. Params: 'target_path'
	@echo "Performing static analysis of source tree..."
	@pipenv run ruff check --target-version $(ruff_target_python) --diff --exit-zero *.py
	@pipenv run ruff check --target-version $(ruff_target_python) --diff --exit-zero $(package_path)
	@pipenv run ruff check --target-version $(ruff_target_python) --statistics --exit-zero *.py
	@pipenv run ruff check --target-version $(ruff_target_python) --statistics --exit-zero $(package_path)

release: update_requirements documentation update_formatting static_analysis  ## Performs bookkeeping necessary for a new release
release:
	@echo "Created new release"

test:  ## Run tests
	@PYTHONPATH=${PYTHON_PATH}:./src pipenv run python runtests.py

test-container:  ## Run tests in a container
	@docker-compose up -d elasticsearch
	@docker-compose build test
	@docker-compose run --rm test make test

upload-dist: install  ## Builds and uploads distribution
	@rm -r ./build || echo "No existing build assets to remove..."  # clean any existing build path assets
	curl -XGET https://packages.wdt.pdx.edu/publish.sh | VENV=$(pipenv) BUILD_TYPE=bdist_wheel bash -
	@rm -rf ./*.egg-info
