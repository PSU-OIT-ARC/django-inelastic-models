FROM python:3.11-bookworm
LABEL org.opencontainers.image.authors="tlinton@pdx.edu"
LABEL org.opencontainers.image.source=https://github.com/PSU-OIT-ARC/django-inelastic-models
ARG APP_VERSION
LABEL org.opencontainers.image.version="${APP_VERSION}"

#############################
#                           #
#  Django Inelastic Models  #
#  Testing image            #
#                           #
#############################


# Install identified dependencies required by application
RUN apt-get update && apt-get install -y \
    build-essential automake

# Configure system default locale
RUN echo "en_US.UTF-8 UTF-8" > /etc/locale.gen
RUN apt install -y locales
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8

# Configure timezone
RUN ln -sf /usr/share/zoneinfo/US/Pacific /etc/localtime
RUN echo "Date: " ; date

# Cleanup after ourselves
RUN apt autoclean && apt clean

#
#
#

# Set build arguments
ARG APP_PYTHON=python3.11
ARG APP_ENV=/opt/venv

# Export build arguments as environment variables
ENV APP_PYTHON=${APP_PYTHON}
ENV APP_ENV=${APP_ENV}

# Prepare virtual environment
COPY /Pipfile /
COPY /Pipfile.lock /

# Configure pipenv and python virtual environment
ENV PIPENV_CUSTOM_VENV_NAME=${APP_ENV}
RUN pip install pipenv

# Create custom virtual environment
RUN ${APP_PYTHON} -m venv ${APP_ENV}
# Install all dependencies from Pipfile.lock
RUN pipenv sync --dev
# Purge pip package cache
RUN ${APP_ENV}/bin/pip cache purge

# Prepare container entrypoint
WORKDIR /django-inelastic-models
