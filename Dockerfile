FROM python:3-alpine

RUN mkdir -p /tmp/plumber

WORKDIR /tmp/plumber

COPY . .

RUN apk update && \
	apk add curl git alpine-sdk libffi-dev openssl-dev openssh-client && \
	curl -LO https://storage.googleapis.com/kubernetes-release/release/`curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt`/bin/linux/amd64/kubectl && \
	chmod +x ./kubectl && \
	mv ./kubectl /usr/local/bin/kubectl && \
	pip install ansible && \
	pip install . && \
	apk del alpine-sdk

ENTRYPOINT ["plumber"]