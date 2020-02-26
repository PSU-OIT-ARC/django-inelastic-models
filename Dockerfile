FROM python:3.6
MAINTAINER Thom Linton <tlinton@pdx.edu>


RUN apt-get update && \
    apt-get install -y make libgdal20
WORKDIR /django-inelastic-models
COPY entrypoint.sh /entrypoint.sh
RUN chmod a+x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
