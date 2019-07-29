import re
import subprocess
import yaml
import plumber

from git import Repo
from terminaltables import AsciiTable

from plumber.common import current_path, LOG, evaluate_expression, ConfigError, \
  ExecutionFailure, DIFF, BRANCH, ACTIVE, TARGET, EXPRESSION, COMMIT, ID, PATH, \
  STEPS, BATCH, TIMEOUT, RETURN_CODE, STEP, STDOUT, STDERR, ACTIONS, TYPE, \
  LOCALDIFF, GLOBAL, CHECKPOINTING, UNIT, CONDITIONS, CONDITION, ALWAYS, \
  FAILURE, SUCCESS, PREHOOK, POSTHOOK, PIPES, get_or_default, \
  create_execution_log, DETECTED, SINGLE, STATUS, UNKNOWN, EXECUTED, \
  NOT_DETECTED, PIPE, FAILED, GITMOJI, UTF8, PLUMBER_LOGS
from plumber.interfaces import Conditional
from plumber.io import create_checkpoint_store


class LocalDiffConditional(Conditional):

  def __init__(self):
    self.target_diffs = None
    self.active_branch = None
    self.target_branch = None
    self.repo = None
    self.checkpoint = None
    self.expression = None
    self.result = None
    self.id = None
    self.new_checkpoint = None

  def configure(self, config, checkpoint):
    self.id = get_or_default(config, ID, None, str)
    if self.id is None:
      raise ConfigError('id not specified:\n{}'.format(yaml.dump(config)))
    self.target_diffs = get_or_default(config, DIFF, None, list)
    if self.target_diffs is None:
      raise ConfigError(
          'No diffs specified in the localdiff condition:\n{}'.format(
              yaml.dump(config)))

    branches = get_or_default(config, BRANCH, None, dict)
    if branches is not None:
      self.active_branch = get_or_default(branches, ACTIVE, None, str)
      self.target_branch = get_or_default(branches, TARGET, None, str)
    self.repo = Repo(current_path())
    self.new_checkpoint = str(self.repo.head.commit)
    self.checkpoint = checkpoint
    self.expression = get_or_default(config, EXPRESSION, None, str)

  def evaluate(self):
    if self.result is None:
      if self.active_branch is not None and str(
          self.repo.active_branch) != self.active_branch:
        LOG.info(
            '[{}] Not on active branch, conditional disabled'.format(self.id))
        self.result = False
        return self.result
      if self.target_branch is not None and str(
          self.repo.active_branch) != self.target_branch:
        previous_branch = str(self.repo.active_branch)
        try:
          LOG.info('[{}] checking out target branch {}'.format(self.id,
                                                               self.target_branch))
          self.repo.git.checkout(self.target_branch)
          self.result = self._has_diff()
        finally:
          self.repo.git.checkout(previous_branch)
      else:
        self.result = self._has_diff()
    return self.result

  def create_checkpoint(self):
    LOG.info(
        '[{}] New checkpoint {}'.format(self.id, self.new_checkpoint))
    return {COMMIT: self.new_checkpoint}

  def _get_diffs_from_current(self):
    if COMMIT not in self.checkpoint:
      return None
    diff_paths = set()
    commit_found = False
    for commit in self.repo.iter_commits():
      diffs = self.repo.head.commit.diff(commit)
      for diff in diffs:
        diff_paths.add(diff.a_rawpath.decode(UTF8))
      commit_found = str(commit) == self.checkpoint[COMMIT]
      if commit_found:
        break
    if not commit_found:
      LOG.warn(
          '[{}] traversed all git log, checkpoint commit not found'.format(
              self.id))
    LOG.info(
        '[{}] detected diffs since last run:\n{}\n'.format(self.id, ''.join(
            f'\n\t {l}' for l in diff_paths)))
    return diff_paths

  def _has_diff(self):
    if COMMIT not in self.checkpoint:
      LOG.warning('[{}] no checkpoint found, pipe will be executed')
      return True
    if self.expression is not None:
      LOG.info(
          '[{}] detecting through expression evaluation: {}'.format(self.id,
                                                                    self.expression))
      return self._has_diff_expression()
    else:
      LOG.info('[{}] detecting any of the diffs'.format(self.id))
      return self._has_diff_all()

  def _has_diff_expression(self):
    diffs = self._get_diffs_from_current()
    exp_dict = {}
    for target_diff in self.target_diffs:
      if type(target_diff) is not dict:
        raise ConfigError('Invalid diff configuration specified:\n{}'.format(
            yaml.dump(target_diff)))
      id = get_or_default(target_diff, ID, None, str)
      if id is not None:
        path = get_or_default(target_diff, PATH, None, str)
        if path is not None:
          for detected_diff in diffs:
            if re.match(target_diff[PATH], detected_diff):
              LOG.info('[{}] path pattern {} matches {}'.format(self.id,
                                                                target_diff[
                                                                  PATH],
                                                                detected_diff))
              exp_dict[id] = True
              break
          if id not in exp_dict:
            exp_dict[id] = False
    return evaluate_expression(self.expression, exp_dict)

  def _has_diff_all(self):
    diffs = self._get_diffs_from_current()
    for target_diff in self.target_diffs:
      if type(target_diff) is not dict:
        raise ConfigError(
            'Invalid diff configuration specified:\n{}'.format(
                yaml.dump(target_diff)))
      for detected_diff in diffs:
        path = get_or_default(target_diff, PATH, None, str)
        if path is not None:
          if re.match(path, detected_diff):
            LOG.info('[{}] path pattern {} matches {}'.format(self.id, path,
                                                              detected_diff))
            return True
    return False


class Executor:

  def __init__(self):
    self.config = None
    self.steps = None
    self.batch = False
    self.timeout = None
    self.results = None

  def configure(self, config):
    self.config = config
    self.steps = get_or_default(config, STEPS, None, list)
    if self.steps is None:
      raise ConfigError(
          'No steps specified to execute:\n{}'.format(yaml.dump(config)))
    self.batch = get_or_default(config, BATCH, False, bool)
    self.timeout = get_or_default(config, TIMEOUT, None, int)
    self.results = []

  def execute(self):
    if self.steps is not None:
      if self.batch:
        script = ''.join(f'\n {l}' for l in self.steps)
        result = self._run_script(script=script)
        self.results.append(result)
        if result[RETURN_CODE] != 0:
          LOG.error(create_execution_log(result))
          raise ExecutionFailure(
              'Step \n{} exited with code {}'.format(script,
                                                     result[RETURN_CODE]))
        else:
          LOG.log(PLUMBER_LOGS, create_execution_log(result))
      else:
        for step in self.steps:
          result = self._run_script(script=step)
          self.results.append(result)
          if result[RETURN_CODE] != 0:
            LOG.error(create_execution_log(result))
            raise ExecutionFailure(
                'Step {} exited with code {}'.format(step, result[RETURN_CODE]))
          else:
            LOG.log(PLUMBER_LOGS, create_execution_log(result))

  def get_results(self):
    return self.results

  def _run_script(self, script):
    kwargs = {'shell': True, 'capture_output': True}
    if self.timeout is not None:
      kwargs['timeout'] = self.timeout
    try:
      proc = subprocess.run([script], **kwargs)
      return {
        STEP: script,
        RETURN_CODE: proc.returncode,
        STDOUT: proc.stdout,
        STDERR: proc.stderr
      }
    except subprocess.TimeoutExpired as e:
      return {
        STEP: script,
        RETURN_CODE: 130,
        STDOUT: e.stdout,
        STDERR: '{} \nStep execution timed out after {} seconds'.format(
            e.stderr, e.timeout).encode(UTF8)

      }


class Hooked:

  def __init__(self):
    self.prehooks = None
    self.posthooks = None
    self.posthooks_success = None
    self.posthooks_failure = None

  def configure(self, config):
    prehooks = get_or_default(config, PREHOOK, None, list)
    if prehooks is not None:
      self.prehooks = []
      for prehook_config in prehooks:
        executor = Executor()
        executor.configure(prehook_config)
        self.prehooks.append(executor)
    posthooks = get_or_default(config, POSTHOOK, None, list)
    if posthooks is not None:
      self.posthooks = []
      self.posthooks_success = []
      self.posthooks_failure = []
      for posthook_config in posthooks:
        executor = Executor()
        executor.configure(posthook_config)
        condition = get_or_default(posthook_config, CONDITION, ALWAYS,
                                   str).lower()
        if condition == ALWAYS:
          self.posthooks.append(executor)
        elif condition == FAILURE:
          self.posthooks_failure.append(executor)
        elif condition == SUCCESS:
          self.posthooks_success.append(executor)
        else:
          raise ConfigError(
              'Invalid execution condition specified on prehook: {}'.format(
                  condition))

  def run_prehooks(self):
    if self.prehooks is not None:
      for hook in self.prehooks:
        hook.execute()

  def run_posthooks(self, last_result):
    if self.posthooks is not None:
      for hook in self.posthooks:
        hook.execute()
    if last_result == SUCCESS and self.posthooks_success is not None:
      for hook in self.posthooks_success:
        hook.execute()
    if last_result == FAILURE and self.posthooks_failure is not None:
      for hook in self.posthooks_failure:
        hook.execute()

  def wrap_in_hooks(self, original, finalization=None):
    def hook_wrapper(*args, **kwargs):
      final_result = SUCCESS
      self.run_prehooks()
      try:
        return original(*args, **kwargs)
      except Exception as e:
        final_result = FAILURE
        raise e
      finally:
        self.run_posthooks(final_result)
        if finalization is not None:
          finalization(final_result)

    return hook_wrapper


def _create_conditional(config, checkpoint):
  if TYPE in config and type(config[TYPE]) is str:
    if config[TYPE].lower() == LOCALDIFF:
      conditional = LocalDiffConditional()
    else:
      raise ConfigError(
          'Invalid condition type specified:\n{}'.format(yaml.dump(config)))
  else:
    conditional = LocalDiffConditional()
  conditional.configure(config, checkpoint)
  return conditional


class PlumberPipe(Hooked):

  def __init__(self):
    super(PlumberPipe, self).__init__()
    self.config = None
    self.conditions = None
    self.actions = None
    self.checkpoint = None

  def configure(self, config, checkpoint):
    super(PlumberPipe, self).configure(config=config)
    id = get_or_default(config, ID, None, str)
    if id is None:
      raise ConfigError(
          'Id not specified for pipe in configuration file:\n{}'.format(
              yaml.dump(config)))
    self.config = config
    self.checkpoint = checkpoint
    conditions = get_or_default(config, CONDITIONS, None, list)
    if conditions is not None:
      self.conditions = []
      declared_conditions = set()
      for condition_config in conditions:
        id = get_or_default(condition_config, ID, None, str)
        if id is None:
          raise ConfigError(
              'Id not specified for condition in the configuration file:\n{}'.format(
                  yaml.dump(condition_config)))
        if id in declared_conditions:
          raise ConfigError(
              'Multiple conditions specified with the id: {}\n'.format(id,
                                                                       yaml.dump(
                                                                           condition_config)))
        declared_conditions.add(id)
        self.conditions.append({ID: id,
                                CONDITION: _create_conditional(condition_config,
                                                               get_or_default(
                                                                   checkpoint,
                                                                   id, {},
                                                                   dict))})
    actions = get_or_default(config, ACTIONS, None, dict)
    if actions is not None:
      self.actions = Executor()
      self.actions.configure(actions)

  def evaluate(self):
    expression = get_or_default(self.config, EXPRESSION, None, str)
    if expression is not None:
      exp_values = {}
      for condition in self.conditions:
        exp_values[condition[ID]] = condition[CONDITION].evaluate()
      return evaluate_expression(expression, exp_values)
    else:
      for condition in self.conditions:
        if condition[CONDITION].evaluate():
          return True
      return False

  def execute(self):
    self.actions.execute()

  def get_new_checkpoint(self):
    for condition in self.conditions:
      self.checkpoint[condition[ID]] = condition[
        CONDITION].create_checkpoint()
    return self.checkpoint

  def run_prehooks(self):
    if self.prehooks is not None:
      LOG.log(PLUMBER_LOGS, wrap_in_dividers(
          "Running prehooks for {}".format(self.config[ID]),
          divider_char='-'))
      super(PlumberPipe, self).run_prehooks()

  def run_posthooks(self, last_result):
    if self.posthooks is not None or (
        last_result == SUCCESS and self.posthooks_success is not None) or (
        last_result == FAILURE and self.posthooks_failure is not None):
      LOG.log(PLUMBER_LOGS, wrap_in_dividers(
          "Running posthooks for {}".format(self.config[ID]),
          divider_char='-'))
      super(PlumberPipe, self).run_posthooks(last_result)


class PlumberPlanner(Hooked):

  def __init__(self, config):
    super(PlumberPlanner, self).__init__()
    self.config = config
    self.checkpoint_store = None
    self.pipes = None
    self.results = None
    self.checkpoint_unit = SINGLE
    global_config = get_or_default(config, GLOBAL, None, dict)
    if global_config is not None:
      super(PlumberPlanner, self).configure(global_config)
      checkpointing_config = get_or_default(global_config, CHECKPOINTING, None,
                                            dict)
      if checkpointing_config is not None:
        checkpoint_unit = get_or_default(checkpointing_config, UNIT, 'single',
                                         str)
        if checkpoint_unit is not None:
          self.checkpoint_unit = checkpoint_unit.lower()
        self.checkpoint_store = create_checkpoint_store(checkpointing_config)
      else:
        self.checkpoint_store = create_checkpoint_store()
    else:
      self.checkpoint_store = create_checkpoint_store()
    self.current_checkpoint = self.checkpoint_store.get_data()
    if PIPES in config:
      self.pipes = []
      declared_pipe_ids = set()
      for pipe_config in config[PIPES]:
        if ID not in pipe_config:
          raise ConfigError('Id not specified for pipe in configuration file')
        if pipe_config[ID] in declared_pipe_ids:
          raise ConfigError(
              'Multiple pipes configured with id: {}'.format(pipe_config[ID]))
        declared_pipe_ids.add(pipe_config[ID])
        pipe = PlumberPipe()
        pipe.configure(pipe_config,
                       get_or_default(self.current_checkpoint, pipe_config[ID],
                                      {}))
        self.pipes.append(pipe)

  def run_prehooks(self):
    if self.prehooks is not None:
      LOG.log(PLUMBER_LOGS,
              wrap_in_dividers("Running global prehooks",
                               divider_char='-'))
      super(PlumberPlanner, self).run_prehooks()

  def run_posthooks(self, last_result):
    if self.posthooks is not None or (
        last_result == SUCCESS and self.posthooks_success is not None) or (
        last_result == FAILURE and self.posthooks_failure is not None):
      LOG.log(PLUMBER_LOGS,
              wrap_in_dividers("Running global posthooks",
                               divider_char='-'))
      super(PlumberPlanner, self).run_posthooks(last_result)

  def get_analysis_report(self):
    def get_report():
      return [
        {ID: pipe.config[ID], DETECTED: pipe.wrap_in_hooks(pipe.evaluate)()}
        for pipe in self.pipes]

    return self.wrap_in_hooks(get_report)()

  def init_checkpoint(self, force=False):
    new_checkpoint = {}
    if len(self.current_checkpoint) != 0 and not force:
      raise ExecutionFailure('A checkpoint already exists')
    for pipe in self.pipes:
      new_checkpoint[pipe.config[ID]] = pipe.get_new_checkpoint()
    self.checkpoint_store.save_data(new_checkpoint,
                                    'Initiating a new checkpoint')

  def execute(self, checkpoint=True):

    def save_new_checkpoint(current_result):
      LOG.log(PLUMBER_LOGS, wrap_in_dividers('Checkpointing'))
      if checkpoint and contains_activity(
          self.results) and current_result == SUCCESS or (
          current_result == FAILURE and self.checkpoint_unit == PIPE):
        LOG.log(PLUMBER_LOGS,
                'Changes performed, persisting a new checkpoint...')
        self.checkpoint_store.save_data(self.current_checkpoint,
                                        create_execution_report(self.results,
                                                                gitmojis=True))
      else:
        LOG.log(PLUMBER_LOGS,
                'Skip checkpointing due to inactivity, error or disabling')

    def main_execution_logic():
      self.results = [{ID: pipe.config[ID], STATUS: UNKNOWN, PIPE: pipe} for
                      pipe in self.pipes]
      for item in self.results:
        LOG.log(PLUMBER_LOGS, wrap_in_dividers(
            'Pipe evaluation for [{}]'.format(item[ID])))

        def pipe_execution_logic():
          if item[PIPE].evaluate():
            item[STATUS] = DETECTED
            LOG.log(PLUMBER_LOGS,
                    'Detected change on pipe {}, starting execution'.format(
                        item[ID]))
            item[PIPE].execute()
            LOG.log(PLUMBER_LOGS, 'Steps for pipe {} executed'.format(item[ID]))
            item[STATUS] = EXECUTED
          else:
            LOG.log(PLUMBER_LOGS,
                    'No change detected on pipe {}. Moving on'.format(item[ID]))
            item[STATUS] = NOT_DETECTED
          if item[STATUS] != NOT_DETECTED:
            self.current_checkpoint[item[PIPE].config[ID]] = item[
              PIPE].get_new_checkpoint()

        try:
          item[PIPE].wrap_in_hooks(pipe_execution_logic)()
        except Exception as e:
          item[STATUS] = FAILED
          raise e
      return self.results

    return self.wrap_in_hooks(main_execution_logic, save_new_checkpoint)()


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


def contains_activity(results):
  for result in results:
    if result[STATUS] != NOT_DETECTED:
      return True
  return False


def wrap_in_dividers(message, divider_char='=', breaks=1):
  breaks = ''.join('\n' for _ in range(breaks))
  divider_length = plumber.common.DEFAULT_DIVIDER_LENGTH
  if divider_length is None:
    divider_length = len(message)
  divider = ''.join(f'{divider_char}' for _ in range(divider_length))
  return '{}\n{}\n{}\n{}\n{}'.format(breaks, divider, message, divider, breaks)
