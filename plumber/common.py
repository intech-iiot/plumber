import os
import logging
import yaml
from terminaltables import AsciiTable

REQUIRED = 'required'
PATH = 'path'
NAMESPACE = 'namespace'
NAME = 'name'
DIFF = 'diff'
BRANCH = 'branch'
ACTIVE = 'active'
TARGET = 'target'
COMMIT = 'commit'
EXPRESSION = 'expression'
UTF8 = 'utf-8'
ID = 'id'
SCRIPT = 'script'
STEPS = 'steps'
BATCH = 'batch'
TIMEOUT = 'timeout'
STEP = 'step'
RETURN_CODE = 'rc'
STDOUT = 'stdout'
STDERR = 'stderr'
TYPE = 'type'
LOCALDIFF = 'localdiff'
CONDITIONS = 'conditions'
CONDITION = 'condition'
ACTIONS = 'actions'
GLOBAL = 'global'
CHECKPOINTING = 'checkpointing'
UNIT = 'unit'
CONFIG = 'config'
PREHOOK = 'prehook'
POSTHOOK = 'posthook'
LOCALFILE = 'localfile'
LOCALGIT = 'localgit'
KUBECONFIG = 'kubeconfig'
ALWAYS = 'always'
SUCCESS = 'success'
FAILURE = 'failure'
PIPES = 'pipes'
PIPE = 'pipe'
SCOPE = 'scope'
SINGLE = 'single'
DETECTED = 'detected'
NOT_DETECTED = 'not detected'
FAILED = 'failed'
STATUS = 'status'
UNKNOWN = 'unknown'
EXECUTED = 'executed'

DEFAULT_CHECKPOINT_FILENAME = '.plumber.checkpoint.yml'

GITMOJI = {
  DETECTED: ':heavy_plus_sign:',
  NOT_DETECTED: ':heavy_minus_sign:',
  EXECUTED: ':white_check_mark:',
  FAILED: ':boom:'
}

DEFAULT_DIVIDER_LENGTH = None
PLUMBER_LOGS = 25

LOG = logging.getLogger()


class PlumberError(Exception):
  def __init__(self, message, inner=None):
    self.message = message
    self.inner = inner


class ConfigError(PlumberError):
  pass


class IOError(PlumberError):
  pass


class ExecutionFailure(PlumberError):
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


def get_or_default(config, name, default, value_type=None,
    raise_on_type_mismatch=True):
  if name in config:
    if value_type is not None and type(config[name]) is not value_type:
      if raise_on_type_mismatch:
        raise ConfigError(
            'The value type for {} is {}. It should be {}:\n{}'.format(name,
                                                                       type(
                                                                           config[
                                                                             name]).__name__,
                                                                       value_type.__name__,
                                                                       yaml.dump(
                                                                           config)))
      return default
    return config[name]
  else:
    return default


def evaluate_expression(expression, exp_dict):
  for key in exp_dict:
    exec('{} = {}'.format(key, exp_dict[key]))
  return eval(expression)


def create_execution_log(result):
  return 'STEP: {}\nSTDOUT: \n{}\nSTDERR: \n{}\nRC: {}\n'.format(result[STEP],
                                                                 result[
                                                                   STDOUT].decode(
                                                                     UTF8),
                                                                 result[
                                                                   STDERR].decode(
                                                                     UTF8),
                                                                 result[
                                                                   RETURN_CODE])


def create_execution_report(results, gitmojis=False):
  table = [['SN', 'ID', 'STATUS']]
  for i in range(len(results)):
    status = results[i][STATUS]
    if gitmojis:
      status = '{} {}'.format(status, GITMOJI[status])
    table.append([i + 1, results[i][ID], status])
  return AsciiTable(table_data=table).table


def create_initial_report(report):
  table = [['SN', 'ID', 'CHANGE DETECTED']]
  for i in range(len(report)):
    table.append([i + 1, report[i][ID], report[i][DETECTED]])
  return AsciiTable(table_data=table).table


def wrap_in_dividers(message, divider_char='=', breaks=1):
  breaks = ''.join('\n' for _ in range(breaks))
  divider_length = DEFAULT_DIVIDER_LENGTH
  if divider_length is None:
    divider_length = len(message)
  divider = ''.join(f'{divider_char}' for _ in range(divider_length))
  return '{}\n{}\n{}\n{}\n{}'.format(breaks, divider, message, divider, breaks)
