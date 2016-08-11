python ?= python3.5
venv ?= .env


# setup a virtualenv
.env:
	virtualenv -p $(python) $(venv)
	# pip>8.1.0 do not currently allow successful installation
	# of editable packages.
	# 
	# See: https://mail-archive.com/debian-bugs-dist@lists.debian.org/msg1418435.html
	$(venv)/bin/pip install pip==8.1.0
	$(venv)/bin/pip install .[test]

# run tests
test: $(venv)
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
