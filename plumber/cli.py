import click
import click_log
import plumber.common

click_log.basic_config(plumber.common.LOG)


@click.group(name='plumber')
def cli():
  """A CD/CI tool capable of running arbitrary shell scripts/commands when
     it detects certain configurable conditions to be true.\n
     Maintained by: Intech IIS \n
     """
  pass


@click_log.simple_verbosity_option(plumber.common.LOG)
def get_report():
  pass


@click_log.simple_verbosity_option(plumber.common.LOG)
def execute():
  pass


cli.add_command(get_report)
cli.add_command(execute)
