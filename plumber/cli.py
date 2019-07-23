import click
import click_log
import plumber
import plumber.common
from plumber.core import PlumberPlanner, create_execution_report, \
  create_initial_report, wrap_in_dividers
from plumber.io import YamlEnvFileStore
from plumber.common import PATH, PLUMBER_LOGS
import logging
import pyfiglet

DEFAULT_CONFIG_PATH = 'plumber.yml'

click_log.basic_config(plumber.common.LOG)

import shutil

plumber.common.DEFAULT_DIVIDER_LENGTH = shutil.get_terminal_size().columns


def set_log_level(level):
  if level == 2:
    plumber.common.LOG.setLevel(PLUMBER_LOGS)
  elif level == 3:
    plumber.common.LOG.setLevel(logging.WARN)
  elif level == 4:
    plumber.common.LOG.setLevel(logging.INFO)
  elif level > 4:
    plumber.common.LOG.setLevel(logging.DEBUG)
  else:
    plumber.common.LOG.setLevel(logging.ERROR)


def print_banner():
  click.echo(wrap_in_dividers(
      '{}{}\n{}'.format(pyfiglet.figlet_format('Plumber', font='slant'),
                        'The CD\CI tool for everything', 'Initiating...')))


@click.group(name='plumber')
def cli():
  """A CD/CI tool capable of running arbitrary shell scripts/commands when
     it detects certain configurable conditions to be true.\n
     Maintained by: Intech IIS \n
     """
  pass


@click.command('detect')
@click.option('--cfg', '-c', help='Path tho plumber config file')
@click.option('--verbose', '-v', help='Set the verbosity level', count=True)
def get_report(cfg, verbose):
  """Detect changes and print out a report"""
  try:
    set_log_level(verbose)
    print_banner()
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
    click.echo(wrap_in_dividers('Final Report'))
    click.echo(create_initial_report(report))
  except Exception as e:
    plumber.common.LOG.error(''.join(f'\n{l}' for l in e.args))


@click.command('go')
@click.option('--cfg', '-c', help='Path tho plumber config file')
@click.option('--verbose', '-v', help='Set the verbosity level', count=True)
def execute(cfg, verbose):
  """Detect changes and run CD/CI steps"""
  try:
    set_log_level(verbose)
    print_banner()
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
        click.echo(wrap_in_dividers('Final Report'))
        click.echo(create_execution_report(results))
  except Exception as e:
    plumber.common.LOG.error(''.join(f'\n{l}' for l in e.args))


cli.add_command(get_report)
cli.add_command(execute)
