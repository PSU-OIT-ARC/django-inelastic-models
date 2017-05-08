python ?= python3.5
venv ?= .env


# setup a virtualenv
init:
	$(python) -m venv $(venv)
	$(venv)/bin/pip install .[test]

# run tests
venv=".env-test"
test: init
	$(venv)/bin/python runtests.py

# update WDT PYPI instance
pypi_release: clean $(venv)
	$(venv)/bin/python setup.py bdist_wheel --universal
	@for archive in `ls dist`; do \
            scp dist/$${archive} rc.pdx.edu:/tmp/; \
            ssh rc.pdx.edu chgrp arc /tmp/$${archive}; \
            ssh rc.pdx.edu sg arc -c "\"mv /tmp/$${archive} /vol/www/cdn/pypi/dist/\""; \
        done

# remove junk
clean:
	find . -iname "*.pyc" -or -iname "__pycache__" -delete
	rm -r build | echo "No build artifacts to remove..."
	rm -r dist | echo "No archives to remove..."
