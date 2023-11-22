FROM python:3.11-bookworm
MAINTAINER Thom Linton <tlinton@pdx.edu>


RUN apt-get update && \
    apt-get install -y \
        make build-essential \
        python3-venv

# Set build arguments
ARG APP_PYTHON=python3.11
ARG APP_ENV=/opt/venv

# Export build arguments as environment variables
ENV APP_PYTHON ${APP_PYTHON}
ENV APP_ENV ${APP_ENV}

# Prepare virtual environment
COPY /Pipfile /
COPY /Pipfile.lock /

# 
RUN pip install pipenv

RUN ${APP_PYTHON} -m venv ${APP_ENV}
RUN PIPENV_CUSTOM_VENV_NAME=${APP_ENV} pipenv sync --dev
RUN PIPENV_CUSTOM_VENV_NAME=${APP_ENV} pipenv check
RUN ${APP_ENV}/bin/pip cache purge

# Prepare container entrypoint
WORKDIR /django-inelastic-models
