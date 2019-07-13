import os
import re

from kubernetes import client, config as kubeconfig
from kubernetes.client import V1ConfigMap
from kubernetes.client.rest import ApiException
from git import Repo

from plumber.common import ConfigError, IOError, PlumberError, get_or_default, \
  current_path
from plumber.interfaces import DataStore

PATH = 'path'
NAMESPACE = 'namespace'
NAME = 'name'
ON_SUCCESS = 'onsuccess'
COMMIT = 'commit'
TAG = 'tag'


class YamlFileStore(DataStore):

  def __init__(self):
    self.path = None
    import yaml as yml
    self.parser = yml

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


class YamlEnvFileStore(YamlFileStore):

  def __init__(self):
    super().__init__()
    self.pattern = re.compile(r".*\$\{env.([A-Za-z_]*)\}(.*)")

    def envex_constructor(loader, node):
      value = loader.construct_scalar(node)
      envVar, remainingPath = self.pattern.match(value).groups()
      return os.getenv(envVar, '\{env.' + envVar + '\}') + remainingPath

    self.parser.add_implicit_resolver('!envvar', self.pattern,
                                      Loader=self.parser.FullLoader)
    self.parser.add_constructor('!envvar', envex_constructor,
                                Loader=self.parser.FullLoader)


class YamlGitFileStore(YamlFileStore):

  def __init__(self):
    super().__init__()
    self.commit = True
    self.tag = False
    self.repo = None

  def configure(self, config):
    super().configure(config)
    if ON_SUCCESS in config:
      if COMMIT in config[ON_SUCCESS] and not config[ON_SUCCESS][COMMIT]:
        self.commit = False
      if TAG in config[ON_SUCCESS] and config[ON_SUCCESS][TAG]:
        self.tag = True
    self.repo = Repo(path=current_path())

  def save_data(self, content):
    super().save_data(content)
    if self.commit:
      self.repo.git.add(self.path)


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
