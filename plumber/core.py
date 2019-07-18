import re
import subprocess

from git import Repo
from terminaltables import AsciiTable

from plumber.common import current_path, LOG, evaluate_expression, ConfigError, \
  ExecutionFailure, DIFF, BRANCH, ACTIVE, TARGET, EXPRESSION, COMMIT, ID, PATH, \
  STEPS, BATCH, TIMEOUT, RETURN_CODE, STEP, STDOUT, STDERR, ACTIONS, TYPE, \
  LOCALDIFF, GLOBAL, CHECKPOINTING, UNIT, CONDITIONS, CONDITION, ALWAYS, \
  FAILURE, SUCCESS, PREHOOK, POSTHOOK, PIPES, get_or_default, \
  create_execution_log, DETECTED, SINGLE, STATUS, UNKNOWN, EXECUTED, \
  NOT_DETECTED, PIPE
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

  def configure(self, config, checkpoint):
    if DIFF in config:
      self.target_diffs = config[DIFF]
    if BRANCH in config:
      if ACTIVE in config[BRANCH]:
        self.active_branch = config[BRANCH][ACTIVE]
      if TARGET in config[BRANCH]:
        self.target_branch = config[BRANCH][TARGET]
    self.repo = Repo(current_path())
    self.checkpoint = checkpoint
    if EXPRESSION in config:
      self.expression = config[EXPRESSION]

  def evaluate(self):
    if self.result is None:
      if self.active_branch is not None and str(
          self.repo.active_branch) != self.active_branch:
        self.result = False
      if self.target_branch is not None and str(
          self.repo.active_branch) != self.target_branch:
        previous_branch = str(self.repo.active_branch)
        try:
          self.repo.git.checkout(self.target_branch)
          self.result = self._has_diff()
        finally:
          self.repo.git.checkout(previous_branch)
      else:
        self.result = self._has_diff()
    return self.result

  def create_checkpoint(self):
    return {COMMIT: str(self.repo.head.commit)}

  def _get_diffs_from_current(self):
    if COMMIT not in self.checkpoint:
      return None
    diff_paths = set()
    for commit in self.repo.iter_commits():
      diffs = self.repo.head.commit.diff(commit)
      for diff in diffs:
        diff_paths.add(diff)
      if str(commit) == self.checkpoint[COMMIT]:
        break
    LOG.warn('Traversed all git log, checkpoint commit not found')
    return diff_paths

  def _has_diff(self):
    if COMMIT not in self.checkpoint:
      return True
    if self.expression is not None:
      return self._has_diff_expression()
    else:
      return self._has_diff_all()

  def _has_diff_expression(self):
    diffs = self._get_diffs_from_current()
    exp_dict = {}
    for target_diff in self.target_diffs:
      if ID in target_diff:
        for detected_diff in diffs:
          if PATH in target_diff:
            if re.match(target_diff[PATH], detected_diff.a_rawpath):
              exp_dict[target_diff[ID]] = True
            else:
              exp_dict[target_diff[ID]] = False
    return evaluate_expression(self.expression, exp_dict)

  def _has_diff_all(self):
    diffs = self._get_diffs_from_current()
    for target_diff in self.target_diffs:
      for detected_diff in diffs:
        if PATH in target_diff:
          if re.match(target_diff[PATH], detected_diff.a_rawpath):
            return True


class Executor:

  def __init__(self):
    self.config = None
    self.steps = None
    self.batch = False
    self.timeout = None
    self.results = None

  def configure(self, config):
    self.config = config
    if STEPS in config:
      self.steps = config[STEPS]
    if BATCH in config and config[BATCH].lower() == 'true':
      self.batch = True
    if TIMEOUT in config:
      self.timeout = int(config[TIMEOUT])
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
              'Step {} exited with code {}'.format(script, result[RETURN_CODE]))
        else:
          LOG.info(create_execution_log(result))
      else:
        for step in self.steps:
          result = self._run_script(script=step)
          self.results.append(result)
          if result[RETURN_CODE] != 0:
            LOG.error(create_execution_log(result))
            raise ExecutionFailure(
                'Step {} exited with code {}'.format(step, result[RETURN_CODE]))
          else:
            LOG.info(create_execution_log(result))

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
            e.stderr, e.timeout)

      }


class Hooked:

  def __init__(self):
    self.prehooks = None
    self.posthooks = None
    self.posthooks_success = None
    self.posthooks_failure = None

  def configure(self, config):
    if PREHOOK in config:
      self.prehooks = []
      for prehook_config in config[PREHOOK]:
        executor = Executor()
        executor.configure(prehook_config)
        self.prehooks.append(executor)
    if POSTHOOK in config:
      self.posthooks = []
      self.posthooks_success = []
      self.posthooks_failure = []
      for posthook_config in config[POSTHOOK]:
        executor = Executor()
        executor.configure(posthook_config)
        if CONDITION in posthook_config:
          condition = posthook_config[CONDITION].lower()
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
        else:
          self.posthooks.append(executor)

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
  if TYPE in config:
    if config[TYPE].lower() == LOCALDIFF:
      conditional = LocalDiffConditional()
    else:
      raise ConfigError('Invalid condition type specified')
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
    if ID not in config:
      raise ConfigError('Id not specified for pipe in configuration file')
    self.config = config
    self.checkpoint = checkpoint
    if CONDITIONS in config:
      self.conditions = []
      for condition_config in config[CONDITIONS]:
        if ID not in condition_config:
          raise ConfigError(
              'Id not specified for a condition in the configuration file')
        self.conditions.append({ID: condition_config[ID], CONDITION:
          _create_conditional(condition_config,
                              get_or_default(checkpoint, condition_config[ID],
                                             {}))})
    if ACTIONS in config:
      self.actions = Executor()
      self.actions.configure(config[ACTIONS])

  def evaluate(self):
    if EXPRESSION in self.config:
      exp_values = {}
      for condition in self.conditions:
        exp_values[condition[ID]] = condition[CONDITION].evaluate()
      return evaluate_expression(self.config[EXPRESSION], exp_values)
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
      LOG.info("Plumber: Running prehooks for {}".format(self.config[ID]))
      super(PlumberPipe, self).run_prehooks()

  def run_posthooks(self, last_result):
    if self.posthooks is not None or (
        last_result == SUCCESS and self.posthooks_success is not None) or (
        last_result == FAILURE and self.posthooks_failure is not None):
      LOG.info("Plumber: Running posthooks for {}".format(self.config[ID]))
      super(PlumberPipe, self).run_posthooks(last_result)


class PlumberPlanner(Hooked):

  def __init__(self, config):
    super(PlumberPlanner, self).__init__()
    super(PlumberPlanner, self).configure(config)
    self.config = config
    self.checkpoint_store = None
    self.pipes = None
    self.results = None
    self.checkpoint_unit = SINGLE
    if GLOBAL in config:
      if CHECKPOINTING in config[GLOBAL]:
        if UNIT in config[GLOBAL][CHECKPOINTING]:
          self.checkpoint_unit = config[GLOBAL][CHECKPOINTING][UNIT]
        self.checkpoint_store = create_checkpoint_store(
            config[GLOBAL][CHECKPOINTING])
    self.current_checkpoint = self.checkpoint_store.get_data()
    if PIPES in config:
      self.pipes = []
      for pipe_config in config[PIPES]:
        if ID not in pipe_config:
          raise ConfigError('Id not specified for pipe in configuration file')
        pipe = PlumberPipe()
        pipe.configure(pipe_config,
                       get_or_default(self.current_checkpoint, pipe_config[ID],
                                      {}))
        self.pipes.append(pipe)

  def run_prehooks(self):
    if self.prehooks is not None:
      LOG.info("Plumber: Running global prehooks")
      super(PlumberPlanner, self).run_prehooks()

  def run_posthooks(self, last_result):
    if self.posthooks is not None or (
        last_result == SUCCESS and self.posthooks_success is not None) or (
        last_result == FAILURE and self.posthooks_failure is not None):
      LOG.info("Plumber: Running global posthooks")
      super(PlumberPlanner, self).run_posthooks(last_result)

  def get_analysis_report(self):
    final_result = SUCCESS
    self.run_prehooks()
    try:
      return [
        {ID: pipe.config[ID], DETECTED: pipe.wrap_in_hooks(pipe.evaluate)()}
        for pipe in self.pipes]
    except Exception as e:
      final_result = FAILURE
      raise e
    finally:
      self.run_posthooks(final_result)

  def execute(self):
    def save_new_checkpoint(current_result):
      if current_result == SUCCESS or (
          current_result == FAILURE and self.checkpoint_unit == PIPE):
        self.checkpoint_store.save_data(self.current_checkpoint,
                                        create_text_report(self.results))

    def main_execution_logic():
      self.results = [{ID: pipe.config[ID], STATUS: UNKNOWN, PIPE: pipe} for
                      pipe in self.pipes]
      for item in self.results:
        def pipe_execution_logic():
          if item[PIPE].evaluate():
            item[STATUS] = DETECTED
            item[PIPE].execute()
            item[STATUS] = EXECUTED
          else:
            item[STATUS] = NOT_DETECTED
          self.current_checkpoint[item[PIPE].config[ID]] = item[
            PIPE].get_new_checkpoint()

        item[PIPE].wrap_in_hooks(pipe_execution_logic)()
      return self.results

    return self.wrap_in_hooks(main_execution_logic, save_new_checkpoint)()


def create_text_report(results):
  table = [['SN', 'ID', 'STATUS']]
  for i in range(len(results)):
    table.append([i, results[i][ID], results[i][STATUS]])
  return AsciiTable(table_data=table).table
