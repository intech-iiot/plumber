import click
import click_log
import plumber
import plumber.common
from plumber.core import PlumberPlanner, create_execution_report, \
  wrap_in_dividers
from plumber.io import YamlEnvFileStore
from plumber.common import PATH, PLUMBER_LOGS
import logging
import pyfiglet
import sys

DEFAULT_CONFIG_PATH = 'plumber.yml'

click_log.basic_config(plumber.common.LOG)

import shutil

plumber.common.DEFAULT_DIVIDER_LENGTH = shutil.get_terminal_size().columns


def set_logging(level, log_file):
  if log_file:
    plumber.common.LOG.addHandler(logging.FileHandler('plumber.log'))
  if level == 1:
    plumber.common.LOG.setLevel(PLUMBER_LOGS)
  elif level == 2:
    plumber.common.LOG.setLevel(logging.INFO)
  elif level > 2:
    plumber.common.LOG.setLevel(logging.DEBUG)
  else:
    plumber.common.LOG.setLevel(logging.WARN)


def print_banner():
  if plumber.common.LOG.level < logging.WARN:
    click.echo(wrap_in_dividers(
        '{}{}\n{}'.format(pyfiglet.figlet_format('Plumber', font='slant'),
                          'The CD\CI tool you deserve :)', 'Initiating...')))


def get_planner(cfg, verbose, log_file):
  set_logging(verbose, log_file)
  print_banner()
  if cfg is None:
    cfg = DEFAULT_CONFIG_PATH
  config_store = YamlEnvFileStore()
  config_store.configure({PATH: cfg})
  config = config_store.get_data()
  if config is None or len(config) == 0:
    plumber.common.LOG.error('Configuration not found')
    sys.exit(1)
  return PlumberPlanner(config)


@click.group(name='plumber')
def cli():
  """A CD/CI tool capable of running arbitrary shell scripts/commands when
     it detects certain configurable conditions to be true.\n
     Maintained by: Intech IIS \n
     """
  pass


@click.command('status')
@click.option('--cfg', '-c', help='Path to plumber config file')
@click.option('--verbose', '-v', help='Set the verbosity level', count=True)
@click.option('--log-file', '-l', help='Create an output log file',
              is_flag=True, default=False)
def get_report(cfg, verbose, log_file):
  """Detect changes and print out a report"""
  try:
    planner = get_planner(cfg, verbose, log_file)
    report = planner.get_analysis_report()
    if plumber.common.LOG.level < logging.WARN:
      click.echo(wrap_in_dividers('Final Report'))
    click.echo(plumber.common.create_initial_report(report))
  except Exception as e:
    plumber.common.LOG.error(''.join(f'\n{l}' for l in e.args))
    sys.exit(1)


@click.command('init')
@click.option('--cfg', '-c', help='Path to plumber config file')
@click.option('--force', '-f', is_flag=True,
              help='Force checkpoint creation, overwrite existing')
@click.option('--verbose', '-v', help='Set the verbosity level', count=True)
@click.option('--log-file', '-l', help='Create an output log file',
              is_flag=True, default=False)
def init(cfg, force, verbose, log_file):
  """Initiate a new checkpoint"""
  try:
    planner = get_planner(cfg, verbose, log_file)
    planner.init_checkpoint(force)
  except Exception as e:
    plumber.common.LOG.error(''.join(f'\n{l}' for l in e.args))
    sys.exit(1)


@click.command('go')
@click.option('--cfg', '-c', help='Path to plumber config file')
@click.option('--no-checkpoint', '-n', is_flag=True,
              help='Do not create the checkpoint')
@click.option('--verbose', '-v', help='Set the verbosity level', count=True)
@click.option('--log-file', '-l', help='Create an output log file',
              is_flag=True, default=False)
def execute(cfg, no_checkpoint, verbose, log_file):
  """Detect changes and run CD/CI steps"""
  try:
    planner = get_planner(cfg, verbose, log_file)
    results = None
    try:
      results = planner.execute(not no_checkpoint)
    finally:
      if results is not None:
        if plumber.common.LOG.level < logging.WARN:
          click.echo(wrap_in_dividers('Final Report'))
        click.echo(create_execution_report(results))
  except Exception as e:
    plumber.common.LOG.error(''.join(f'\n{l}' for l in e.args))
    sys.exit(1)


cli.add_command(get_report)
cli.add_command(execute)
cli.add_command(init)

if __name__ == '__main__':
  cli()
