import click
import click_log
import plumber.common
from plumber.core import PlumberPlanner, create_execution_report, \
  create_initial_report
from plumber.io import YamlEnvFileStore
from plumber.common import PATH
import logging

DEFAULT_CONFIG_PATH = 'plumber.yml'

click_log.basic_config(plumber.common.LOG)


def set_log_level(level):
  if level == 2:
    plumber.common.LOG.setLevel(logging.WARN)
  elif level == 3:
    plumber.common.LOG.setLevel(logging.INFO)
  elif level > 3:
    plumber.common.LOG.setLevel(logging.DEBUG)
  else:
    plumber.common.LOG.setLevel(logging.ERROR)


@click.group(name='plumber')
def cli():
  """A CD/CI tool capable of running arbitrary shell scripts/commands when
     it detects certain configurable conditions to be true.\n
     Maintained by: Intech IIS \n
     """
  pass


@click.command('report')
@click.option('--cfg', '-c', help='Path tho plumber config file')
@click.option('--verbose', '-v', help='Set the verbosity level', count=True)
def get_report(cfg, verbose):
  set_log_level(verbose)
  if cfg is None:
    cfg = DEFAULT_CONFIG_PATH
  config_store = YamlEnvFileStore()
  config_store.configure({PATH: cfg})
  config = config_store.get_data()
  if config is None or len(config) == 0:
    plumber.common.LOG.error('Configuration not found')
    return
  planner = PlumberPlanner(config)
  report = planner.get_analysis_report()
  click.echo(create_initial_report(report))


@click.command('go')
@click.option('--cfg', '-c', help='Path tho plumber config file')
@click.option('--verbose', '-v', help='Set the verbosity level', count=True)
def execute(cfg, verbose):
  set_log_level(verbose)
  if cfg is None:
    cfg = DEFAULT_CONFIG_PATH
  config_store = YamlEnvFileStore()
  config_store.configure({PATH: cfg})
  config = config_store.get_data()
  if config is None or len(config) == 0:
    plumber.common.LOG.error('Configuration not found')
    return
  planner = PlumberPlanner(config)
  results = None
  try:
    results = planner.execute()
  finally:
    if results is not None:
      click.echo(create_execution_report(results))


cli.add_command(get_report)
cli.add_command(execute)
