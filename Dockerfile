FROM python:3.6
MAINTAINER Thom Linton <tlinton@pdx.edu>


RUN apt-get update && \
    apt-get install -y make libgdal1h
WORKDIR /django-inelastic-models
