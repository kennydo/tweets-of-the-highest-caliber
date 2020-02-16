FROM ubuntu:bionic

MAINTAINER kedo@ocf.berkeley.edu

RUN apt-get update \
    && apt-get install -y software-properties-common \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y \
        tox \
        python3.8


ENV PATH "${PATH}:/code/venv/bin"

WORKDIR /code
ADD tox.ini requirements.txt requirements-dev.txt /code/
ADD tothc /code/tothc

RUN tox -e venv
