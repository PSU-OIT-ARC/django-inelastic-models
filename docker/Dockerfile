FROM python:3.9-bullseye
MAINTAINER Thom Linton <tlinton@pdx.edu>


RUN apt-get update && \
    apt-get install -y \
        make build-essential \
        python3-venv

# Set build arguments
ARG APP_PYTHON=python3.9
ARG APP_ENV=/opt/venv
ARG APP_REQUIREMENTS=requirements.txt

# Export build arguments as environment variables
ENV APP_PYTHON ${APP_PYTHON}
ENV APP_ENV ${APP_ENV}

# Prepare virtual environment package requirements
COPY /${APP_REQUIREMENTS} /requirements.txt

# Prepare virtual environment
RUN mkdir -p ${APP_ENV}
RUN ${APP_PYTHON} -m venv ${APP_ENV}
RUN ${APP_ENV}/bin/pip install --upgrade pip wheel
RUN ${APP_ENV}/bin/pip install -r /requirements.txt
RUN ${APP_ENV}/bin/pip cache purge

WORKDIR /django-inelastic-models
