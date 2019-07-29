from unittest import mock

from kubernetes.client import V1ConfigMap
from kubernetes.client.rest import ApiException

from plumber.common import PATH, ConfigError, DEFAULT_CHECKPOINT_FILENAME, TYPE, \
  CONFIG, LOCALGIT, LOCALFILE, KUBECONFIG
import pytest
import os


def ensure_file_not_exist(path):
  try:
    os.remove(path)
  except Exception:
    pass


def test_yaml_file_store():
  test_dict = {'key': 'value'}
  path = 'yaml-test'
  ensure_file_not_exist(path)
  from plumber.io import YamlFileStore
  yaml_store = YamlFileStore()
  yaml_store.configure({PATH: path})
  saved_data = yaml_store.get_data()
  assert len(saved_data) == 0
  yaml_store.save_data(test_dict)
  yaml_store = YamlFileStore()
  yaml_store.configure({PATH: path})
  saved_data = yaml_store.get_data()
  assert 'key' in saved_data
  assert saved_data['key'] == test_dict['key']


def test_yaml_file_store_no_path():
  try:
    from plumber.io import YamlFileStore
    yaml_store = YamlFileStore()
    yaml_store.configure({'key': 'val'})
    pytest.fail('Store should not be created without any specified path')
  except Exception as e:
    assert type(e) is ConfigError


def test_yaml_env_file_store():
  path = 'yaml-test'
  ensure_file_not_exist(path)
  key, value = get_random_env()
  with open(path, 'w') as file:
    file.write('user: ${env.' + key + '}')
  from plumber.io import YamlEnvFileStore
  yaml_store = YamlEnvFileStore()
  yaml_store.configure({PATH: path})
  saved_data = yaml_store.get_data()
  assert 'user' in saved_data
  assert saved_data['user'] == value


@mock.patch('git.index.base.IndexFile.commit')
@mock.patch('git.remote.Remote.push')
@mock.patch('git.cmd.Git._call_process')
def test_yaml_git_file_store(mock_add, mock_push, mock_commit):
  mock_commit.return_value = None
  mock_push.return_value = None
  mock_add.retutn_value = None
  path = 'test.yml'
  data = {'name': 'i have no name'}
  from plumber.io import YamlGitFileStore
  store = YamlGitFileStore()
  store.configure({PATH: path})
  store.save_data(data, path)
  mock_add.assert_called_once()
  mock_commit.assert_called_once()
  mock_push.assert_called_once()


@mock.patch('kubernetes.config.load_kube_config')
@mock.patch('kubernetes.config.load_incluster_config')
@mock.patch('kubernetes.client.CoreV1Api.read_namespaced_config_map')
@mock.patch('kubernetes.client.CoreV1Api.create_namespaced_config_map')
def test_kube_config_store(create_mock, read_mock, incluster_config_mock,
    config_mock):
  incluster_config_mock.return_value = None
  config_mock.return_value = None
  exception = ApiException()
  exception.status = 404
  read_mock.side_effect = exception
  create_mock.return_value = None
  from plumber.io import KubeConfigStore
  store = KubeConfigStore()
  store.configure({})
  data = store.get_data()
  assert len(data) == 0
  data = {'name': 'i have no name'}
  store.save_data(data)
  read_mock.assert_called()
  read_mock.assert_called_with('plumber-checkpoint', 'default', export=True)
  create_mock.assert_called_once()


@mock.patch('kubernetes.config.load_kube_config')
@mock.patch('kubernetes.config.load_incluster_config')
@mock.patch('kubernetes.client.CoreV1Api.read_namespaced_config_map')
@mock.patch('kubernetes.client.CoreV1Api.replace_namespaced_config_map')
def test_kube_config_store_2(replace_mock, read_mock, incluster_config_mock,
    config_mock):
  existing = V1ConfigMap()
  existing.data = {'name': 'I have no name!'}
  incluster_config_mock.return_value = None
  config_mock.return_value = None
  read_mock.return_value = existing
  replace_mock.return_value = None
  try:
    os.environ['KUBERNETES_SERVICE_HOST'] = '127.0.0.1'
    from plumber.io import KubeConfigStore
    store = KubeConfigStore()
    store.configure({})
    data = store.get_data()
    assert len(data) == 1
    assert data['name'] == existing.data['name']
    data = {'name': 'i have a name now, but i forgot'}
    store.save_data(data)
    read_mock.assert_called()
    read_mock.assert_called_with('plumber-checkpoint', 'default', export=True)
    replace_mock.assert_called_once()
  finally:
    del os.environ['KUBERNETES_SERVICE_HOST']


def test_create_checkpoint_store_file():
  from plumber.io import create_checkpoint_store
  config = {
    TYPE: LOCALFILE,
    CONFIG: {}
  }
  store = create_checkpoint_store(config)
  from plumber.io import YamlFileStore
  assert type(store) == YamlFileStore
  assert store.path == DEFAULT_CHECKPOINT_FILENAME


def test_create_checkpoint_store_file_default_1():
  from plumber.io import create_checkpoint_store
  config = {
    TYPE: LOCALFILE
  }
  store = create_checkpoint_store(config)
  from plumber.io import YamlFileStore
  assert type(store) == YamlFileStore
  assert store.path == DEFAULT_CHECKPOINT_FILENAME


def test_create_checkpoint_store_file_default_2():
  from plumber.io import create_checkpoint_store
  store = create_checkpoint_store({})
  from plumber.io import YamlFileStore
  assert type(store) == YamlFileStore
  assert store.path == DEFAULT_CHECKPOINT_FILENAME


def test_create_checkpoint_store_file_default_3():
  from plumber.io import create_checkpoint_store
  store = create_checkpoint_store(None)
  from plumber.io import YamlFileStore
  assert type(store) == YamlFileStore
  assert store.path == DEFAULT_CHECKPOINT_FILENAME


def test_create_checkpoint_store_git():
  from plumber.io import create_checkpoint_store
  config = {
    TYPE: LOCALGIT,
    CONFIG: {}
  }
  store = create_checkpoint_store(config)
  from plumber.io import YamlGitFileStore
  assert type(store) == YamlGitFileStore
  assert store.path == DEFAULT_CHECKPOINT_FILENAME


@mock.patch('kubernetes.config.load_kube_config')
@mock.patch('kubernetes.config.load_incluster_config')
def test_create_checkpoint_store_kube(config_mock_incluster, config_mock):
  config_mock.return_value = None
  config_mock_incluster.return_value = None
  from plumber.io import create_checkpoint_store
  config = {
    TYPE: KUBECONFIG,
    CONFIG: {}
  }
  store = create_checkpoint_store(config)
  from plumber.io import KubeConfigStore
  assert type(store) == KubeConfigStore
  assert store.configmap_name == 'plumber-checkpoint'
  assert store.namespace == 'default'


def test_initialize_default_checkpoint_store():
  from plumber.io import initialize_default_checkpoint_store, YamlFileStore
  store = initialize_default_checkpoint_store()
  assert type(store) == YamlFileStore
  assert store.path == DEFAULT_CHECKPOINT_FILENAME


def get_random_env():
  for item in os.environ:
    return item, os.environ[item]
