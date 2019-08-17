FROM python:3-slim

RUN mkdir -p /tmp/plumber

WORKDIR /tmp/plumber

COPY . .

RUN apt update && \
	apt install -y curl git && \
	curl -LO https://storage.googleapis.com/kubernetes-release/release/`curl -s https://storage.googleapis.com/kubernetes-release/release/stable.txt`/bin/linux/amd64/kubectl && \
	chmod +x ./kubectl && \
	mv ./kubectl /usr/local/bin/kubectl && \
	pip install ansible && \
	pip install .

ENTRYPOINT ["plumber"]