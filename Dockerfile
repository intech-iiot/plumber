FROM python:3-alpine

ENV KUBERNETES_VERSION=v1.14.1

RUN apk add --update --no-cache curl git alpine-sdk libffi-dev openssl-dev openssh-client && \
	curl -LO https://storage.googleapis.com/kubernetes-release/release/$KUBERNETES_VERSION/bin/linux/amd64/kubectl && \
	chmod +x ./kubectl && \
	mv ./kubectl /usr/local/bin/kubectl && \
	pip install ansible && \
	apk del alpine-sdk

RUN mkdir -p /tmp/plumber

COPY . /tmp/plumber/

RUN pip install /tmp/plumber

ENTRYPOINT ["plumber"]