FROM python:3.7-slim

ENV KUBERNETES_VERSION=v1.14.1

RUN apt-get update && apt-get install -y curl git wget unzip libssl-dev libffi-dev openssh-client && \
	curl -LO https://storage.googleapis.com/kubernetes-release/release/$KUBERNETES_VERSION/bin/linux/amd64/kubectl && \
	chmod +x ./kubectl && \
	mv ./kubectl /usr/local/bin/kubectl && \
	apt-get install -y chromium python-selenium python3-selenium && \
	wget https://chromedriver.storage.googleapis.com/2.35/chromedriver_linux64.zip && \
	unzip chromedriver_linux64.zip && \
	rm chromedriver_linux64.zip && \
	pip install --no-cache-dir ansible selenium pytest
	
RUN mkdir -p /tmp/plumber && \
	mkdir -p /tmp/FEtest

COPY . /tmp/plumber/

RUN pip install --no-cache-dir /tmp/plumber

ENTRYPOINT ["plumber"]
