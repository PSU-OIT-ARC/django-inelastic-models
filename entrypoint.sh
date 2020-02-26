#!/bin/bash
set -e


VENV=".env-test-container"
python3 -m venv ${VENV}
${VENV}/bin/pip install .[test]
${VENV}/bin/python runtests.py
