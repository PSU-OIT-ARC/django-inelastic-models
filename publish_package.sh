#!/bin/bash
set -e


AWS_CLI="`which aws || echo`"
if [[ ! "${AWS_CLI}" ]]; then
    AWS_CLI="docker run --user $(id -u) --rm -i -v ${HOME}/.aws:/.aws -v $(pwd):/aws amazon/aws-cli"
fi

BUCKET_PATH="s3://packages.wdt.pdx.edu/dist/"
GENERATE_INDEX="https://packages.wdt.pdx.edu/generate_index.py"

# build distribution
pipenv run python -m build

# upload distributions
for archive in `ls dist`; do \
    ${AWS_CLI} s3 cp dist/${archive} ${BUCKET_PATH}; \
    rm dist/${archive}; \
    done

# generate new package index
curl -XGET ${GENERATE_INDEX} | pipenv run python -
