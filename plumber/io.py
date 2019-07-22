import os
import re

from git import Repo
from kubernetes import client, config as kubeconfig
from kubernetes.client import V1ConfigMap
from kubernetes.client.rest import ApiException

from plumber.common import ConfigError, IOError, PlumberError, get_or_default, \
  current_path, LOG, PATH, NAME, NAMESPACE, TYPE, CONFIG, LOCALFILE, LOCALGIT, \
  KUBECONFIG, DEFAULT_CHECKPOINT_FILENAME
from plumber.interfaces import DataStore


class YamlFileStore(DataStore):

  def __init__(self):
    self.path = None
    import yaml as yml
    self.parser = yml

  def configure(self, config):
    self.path = get_or_default(config, PATH, None, str)
    if self.path is None:
      raise ConfigError(
          'Path to yaml file not provided:\n{}'.format(
              self.parser.dump(config)))

  def get_data(self):
    try:
      with open(self.path) as file:
        return self.parser.full_load(file)
    except FileNotFoundError as e:
      return {}

  def save_data(self, content, info=None):
    with open(self.path, 'w') as file:
      self.parser.dump(content, file)


class YamlEnvFileStore(YamlFileStore):

  def __init__(self):
    super(YamlEnvFileStore, self).__init__()
    self.pattern = re.compile(r".*\$\{env.([A-Za-z_]*)\}(.*)")

    def envex_constructor(loader, node):
      value = loader.construct_scalar(node)
      envVar, remainingPath = self.pattern.match(value).groups()
      LOG.debug(
          'Found environment variable {}, will be substituted if found'.format(
              envVar))
      return os.getenv(envVar, '\{env.' + envVar + '\}') + remainingPath

    self.parser.add_implicit_resolver('!envvar', self.pattern,
                                      Loader=self.parser.FullLoader)
    self.parser.add_constructor('!envvar', envex_constructor,
                                Loader=self.parser.FullLoader)


class YamlGitFileStore(YamlFileStore):

  def __init__(self):
    super(YamlGitFileStore, self).__init__()
    self.repo = None

  def configure(self, config):
    super().configure(config)
    self.repo = Repo(path=current_path())

  def save_data(self, content, info=None):
    super().save_data(content, info)
    self.repo.git.add(self.path)
    if info is not None:
      self.repo.index.commit(
        ':wrench::construction_worker: [Plumber]\n{}'.format(info))
      origin = self.repo.remote(name='origin')
      origin.push()
    else:
      LOG.error('Commit content not provided')


class KubeConfigStore(DataStore):

  def configure(self, config):
    self.configmap_name = get_or_default(config, NAME, 'plumber-checkpoint',
                                         str)
    self.namespace = get_or_default(config, NAMESPACE, 'default', str)

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
        raise IOError('Could not read data', e)

  def _cm_exists(self):
    try:
      self.core_api.read_namespaced_config_map(self.configmap_name,
                                               self.namespace, export=True)
      return True
    except ApiException as e:
      if e.status == 404:
        return False
      else:
        raise IOError('Could not read data', e)

  def save_data(self, content, info=None):
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
      raise IOError('Could now write data', e)


def create_checkpoint_store(config=None):
  if config is not None:
    store_type = get_or_default(config, TYPE, None, str)
    if store_type is not None:
      store_type = store_type.lower()
      if CONFIG in config:
        store_config = config[CONFIG]
      else:
        store_config = {}
      if store_type == LOCALFILE:
        checkpoint_store = YamlFileStore()
        if PATH not in store_config:
          store_config[PATH] = DEFAULT_CHECKPOINT_FILENAME
      elif store_type == LOCALGIT:
        checkpoint_store = YamlGitFileStore()
        if PATH not in store_config:
          store_config[PATH] = DEFAULT_CHECKPOINT_FILENAME
      elif store_type == KUBECONFIG:
        checkpoint_store = KubeConfigStore()
      else:
        raise ConfigError('Unknown checkpoint type specified')
      checkpoint_store.configure(store_config)
    else:
      checkpoint_store = initialize_default_checkpoint_store()
  else:
    checkpoint_store = initialize_default_checkpoint_store()
  return checkpoint_store


def initialize_default_checkpoint_store():
  LOG.debug('Initialized with default YAML checkpoint store')
  checkpoint_store = YamlFileStore()
  checkpoint_store.configure({PATH: DEFAULT_CHECKPOINT_FILENAME})
  return checkpoint_store
