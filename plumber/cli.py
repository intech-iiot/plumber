import click
import click_log
import plumber.common
from plumber.core import PlumberPlanner
from plumber.io import YamlEnvFileStore
from plumber.common import PATH

DEFAULT_CONFIG_PATH = 'plumber.yml'

click_log.basic_config(plumber.common.LOG)


@click.group(name='plumber')
def cli():
  """A CD/CI tool capable of running arbitrary shell scripts/commands when
     it detects certain configurable conditions to be true.\n
     Maintained by: Intech IIS \n
     """
  pass


@click.command('report')
@click.option('--cfg', '-c', help='Path tho plumber config file')
@click_log.simple_verbosity_option(plumber.common.LOG)
def get_report(cfg):
  if cfg is None:
    cfg = DEFAULT_CONFIG_PATH
  config_store = YamlEnvFileStore()
  config_store.configure({PATH: cfg})
  config = config_store.get_data()
  if config is None or len(config) == 0:
    click.echo('Error: Configuration file empty or not found')
    return
  planner = PlumberPlanner(config)
  click.echo(planner.get_analysis_report())


@click.command('go')
@click.option('--cfg', '-c', help='Path tho plumber config file')
@click_log.simple_verbosity_option(plumber.common.LOG)
def execute(cfg):
  if cfg is None:
    cfg = DEFAULT_CONFIG_PATH
  config_store = YamlEnvFileStore()
  config_store.configure({PATH: cfg})
  config = config_store.get_data()
  if config is None or len(config) == 0:
    click.echo('Error: Configuration file empty or not found')
    return
  planner = PlumberPlanner(config)
  planner.execute()


cli.add_command(get_report)
cli.add_command(execute)
