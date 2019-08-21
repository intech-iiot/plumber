from unittest import mock

from click.testing import CliRunner
from git import Repo

from plumber.cli import cli
from plumber.common import PIPES, ID, CONDITIONS, TYPE, LOCALDIFF, DIFF, PATH, \
  ConfigError, ACTIONS, STEPS


def get_next_commit():
  repo = Repo()
  next = False
  for commit in repo.iter_commits():
    if next:
      return str(commit)
    else:
      next = True


@mock.patch('plumber.io.YamlEnvFileStore.get_data')
@mock.patch('plumber.io.YamlFileStore.save_data')
@mock.patch('plumber.operators.LocalDiffConditional.create_checkpoint')
def test_init(checkpoint_mock, yml_save_mock, env_get_mock):
  CONFIG = {
    PIPES: [
      {
        ID: 'pipe',
        CONDITIONS: [
          {
            ID: 'diff',
            TYPE: LOCALDIFF,
            DIFF: [
              {
                PATH: '.*'
              }
            ]
          }
        ]
      }
    ]
  }
  env_get_mock.return_value = CONFIG
  yml_save_mock.return_value = None
  checkpoint_mock.return_value = {'commit': 'checkpoint'}
  runner = CliRunner()
  result = runner.invoke(cli, ['init'])
  assert result.exit_code == 0
  env_get_mock.assert_called_once()
  yml_save_mock.assert_called_once()
  args = yml_save_mock.call_args[0][0]
  assert args['pipe']['diff']['commit'] == 'checkpoint'


@mock.patch('plumber.io.YamlEnvFileStore.get_data')
def test_init_no_config(env_get_mock):
  CONFIG = {
  }
  env_get_mock.return_value = CONFIG
  runner = CliRunner()
  result = runner.invoke(cli, ['init'])
  assert result.exit_code != 0


@mock.patch('plumber.io.YamlEnvFileStore.get_data')
def test_init_error(env_get_mock):
  env_get_mock.side_effect = ConfigError('Test exception')
  runner = CliRunner()
  result = runner.invoke(cli, ['init'])
  assert result.exit_code != 0


@mock.patch('plumber.io.YamlEnvFileStore.get_data')
@mock.patch('plumber.operators.LocalDiffConditional.evaluate')
def test_status(evaluate_mock, env_get_mock):
  CONFIG = {
    PIPES: [
      {
        ID: 'mypipe',
        CONDITIONS: [
          {
            ID: 'diff',
            TYPE: LOCALDIFF,
            DIFF: [
              {
                PATH: '.*'
              }
            ]
          }
        ]
      }
    ]
  }
  env_get_mock.return_value = CONFIG
  evaluate_mock.return_value = True
  runner = CliRunner()
  result = runner.invoke(cli, ['status'])
  assert result.exit_code == 0
  assert 'mypipe' in result.output
  assert 'True' in result.output
  env_get_mock.assert_called_once()
  evaluate_mock.assert_called_once()


@mock.patch('plumber.io.YamlEnvFileStore.get_data')
def test_status_no_config(env_get_mock):
  CONFIG = {
  }
  env_get_mock.return_value = CONFIG
  runner = CliRunner()
  result = runner.invoke(cli, ['status'])
  assert result.exit_code != 0


@mock.patch('plumber.io.YamlEnvFileStore.get_data')
def test_status_error(env_get_mock):
  env_get_mock.side_effect = ConfigError('Test exception')
  runner = CliRunner()
  result = runner.invoke(cli, ['status'])
  assert result.exit_code != 0


@mock.patch('plumber.io.YamlEnvFileStore.get_data')
@mock.patch('plumber.io.YamlFileStore.save_data')
@mock.patch('plumber.operators.LocalDiffConditional.evaluate')
def test_execute(evaluate_mock, yml_save_mock, env_get_mock):
  CONFIG = {
    PIPES: [
      {
        ID: 'mypipe',
        CONDITIONS: [
          {
            ID: 'diff',
            TYPE: LOCALDIFF,
            DIFF: [
              {
                PATH: '.*'
              }
            ]
          }
        ],
        ACTIONS: {
          STEPS: [
            'echo "Executing CD"'
          ]
        }
      }
    ]
  }
  env_get_mock.return_value = CONFIG
  evaluate_mock.return_value = True
  yml_save_mock.return_value = None
  runner = CliRunner()
  result = runner.invoke(cli, ['go'])
  assert result.exit_code == 0
  assert 'mypipe' in result.output
  assert 'executed' in result.output
  env_get_mock.assert_called_once()
  evaluate_mock.assert_called_once()
  yml_save_mock.assert_called_once()


@mock.patch('plumber.io.YamlEnvFileStore.get_data')
def test_execute_no_config(env_get_mock):
  CONFIG = {
  }
  env_get_mock.return_value = CONFIG
  runner = CliRunner()
  result = runner.invoke(cli, ['go'])
  assert result.exit_code != 0


@mock.patch('plumber.io.YamlEnvFileStore.get_data')
def test_execute_error(env_get_mock):
  env_get_mock.side_effect = ConfigError('Test exception')
  runner = CliRunner()
  result = runner.invoke(cli, ['go'])
  assert result.exit_code != 0
