import os
import logging

REQUIRED = 'required'
LOG = logging.getLogger()


class PlumberError(Exception):
  def __init__(self, message, inner=None):
    self.message = message
    self.inner = inner


class ConfigError(PlumberError):
  pass


class IOError(PlumberError):
  pass


def current_path():
  return os.path.realpath(os.path.join(os.getcwd()))


# Waiting for the fix to merge, until then, go ahead with monkey patching
# https://github.com/kubernetes-client/python-base/issues/84
import time


def _load_azure_token_fixed(self, provider):
  if 'config' not in provider:
    return
  if 'access-token' not in provider['config']:
    return
  if 'expires-on' in provider['config']:
    try:
      if time.gmtime(int(provider['config']['expires-on'])) < time.gmtime():
        self._refresh_azure_token(provider['config'])
    except ValueError:  # sometimes expires-on is not an int, but a datestring
      if time.strptime(provider['config']['expires-on'],
                       '%Y-%m-%d %H:%M:%S.%f') < time.gmtime():
        self._refresh_azure_token(provider['config'])
  self.token = 'Bearer %s' % provider['config']['access-token']
  return self.token


from kubernetes.config.kube_config import KubeConfigLoader

KubeConfigLoader._load_azure_token = _load_azure_token_fixed


def get_or_default(config, name, default):
  if name in config:
    return name
  else:
    return default
