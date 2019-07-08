import os
import re

from kubernetes import client, config as kubeconfig
from kubernetes.client import V1ConfigMap
from kubernetes.client.rest import ApiException

from plumber.common import ConfigError, IOError, PlumberError, get_or_default
from plumber.interfaces import DataStore

PATH = 'path'
NAMESPACE = 'namespace'
NAME = 'name'


class YamlEnvFileStore(DataStore):

  def __init__(self):
    self.path = None
    import yaml as yml
    self.parser = yml
    self.pattern = re.compile(r".*\$\{env.([A-Za-z_]*)\}(.*)")

    def envex_constructor(loader, node):
      value = loader.construct_scalar(node)
      envVar, remainingPath = self.pattern.match(value).groups()
      return os.getenv(envVar, '\{env.' + envVar + '\}') + remainingPath

    self.parser.add_implicit_resolver('!envvar', self.pattern,
                                      Loader=self.parser.FullLoader)
    self.parser.add_constructor('!envvar', envex_constructor,
                                Loader=self.parser.FullLoader)

  def configure(self, config):
    if PATH in config:
      self.path = config[PATH]
    else:
      raise ConfigError('path to yaml file not provided')

  def get_data(self):
    try:
      with open(self.path) as file:
        return self.parser.full_load(file)
    except FileNotFoundError:
      return {}

  def save_data(self, content):
    with open(self.path, 'w') as file:
      self.parser.dump(content, file)


class KubeConfigStore(DataStore):

  def configure(self, config):
    if NAME in config:
      self.configmap_name = config[NAME]
    else:
      raise ConfigError('{} not provided in kubeconfig'.format(NAME))

    self.namespace = get_or_default(config, NAMESPACE, 'default')

    if bool(os.getenv('KUBERNETES_SERVICE_HOST')):
      kubeconfig.load_incluster_config()
    else:
      kubeconfig.load_kube_config()

    self.core_api = client.CoreV1Api()

  def get_data(self):
    try:
      config_map = self.core_api.read_namespaced_config_map(self.configmap_name,
                                                            self.namespace,
                                                            export=True)
      return config_map.data
    except ApiException as e:
      if e.status == 404:
        return {}
      else:
        raise IOError('could not read data', e)

  def _cm_exists(self):
    try:
      self.core_api.read_namespaced_config_map(self.configmap_name,
                                               self.namespace, export=True)
      return True
    except ApiException as e:
      if e.status == 404:
        return False
      else:
        raise IOError('could not read data', e)

  def save_data(self, content):
    try:
      configmap_body = V1ConfigMap(data=content)
      if self._cm_exists():
        self.core_api.replace_namespaced_config_map(self.configmap_name,
                                                    self.namespace,
                                                    configmap_body)
      else:
        self.core_api.create_namespaced_config_map(self.namespace,
                                                   configmap_body)
    except PlumberError:
      raise
    except Exception as e:
      raise IOError('could now write data', e)
