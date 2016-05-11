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
test: .env
	$(venv)/bin/python runtests.py

# remove junk
clean:
	rm -rf $(venv)
	find . -iname "*.pyc" -or -iname "__pycache__" -delete
