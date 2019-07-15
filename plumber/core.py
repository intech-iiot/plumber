import re
import subprocess

from git import Repo

from plumber.common import current_path, LOG, evaluate_expression, ConfigError, \
  ExecutionFailure, DIFF, BRANCH, ACTIVE, TARGET, EXPRESSION, COMMIT, ID, PATH, \
  STEPS, BATCH, TIMEOUT, RETURN_CODE, STEP, STDOUT, STDERR, ACTIONS, TYPE, \
  LOCALDIFF, GLOBAL, CHECKPOINTING, UNIT, CONDITIONS, CONDITION, ALWAYS, \
  FAILURE, SUCCESS, PREHOOK, SCOPE, POSTHOOK, PIPES, get_or_default, \
  create_execution_log, PIPE, DETECTED
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
            break
      return False
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
          raise ExecutionFailure(
              'Step {} exited with code {}'.format(script, result[RETURN_CODE]))
      else:
        for step in self.steps:
          result = self._run_script(script=step)
          self.results.append(result)
          if result[RETURN_CODE] != 0:
            raise ExecutionFailure(
                'Step {} exited with code {}'.format(step, result[RETURN_CODE]))

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


class PlumberPipe:
  def __init__(self):
    self.conditions = None
    self.actions = None
    self.configuration = None
    self.checkpoint = None

  def configure(self, configuration, checkpoint):
    if ID not in configuration:
      raise ConfigError('Id not specified for pipe in configuration file')
    self.configuration = configuration
    self.checkpoint = checkpoint
    if CONDITIONS in configuration:
      self.conditions = []
      for condition_config in configuration[CONDITIONS]:
        if ID not in condition_config:
          raise ConfigError(
              'Id not specified for a condition in the configuration file')
        self.conditions.append({ID: condition_config[ID], CONDITION:
          self._create_conditional(condition_config,
                                   get_or_default(checkpoint,
                                                  condition_config[ID], {}))})
    if ACTIONS in configuration:
      self.actions = Executor()
      self.actions.configure(configuration[ACTIONS])

  def _create_conditional(self, config, checkpoint):
    if TYPE in config:
      if config[TYPE].lower() == LOCALDIFF:
        conditional = LocalDiffConditional()
      else:
        raise ConfigError('Invalid condition type specified')
    else:
      conditional = LocalDiffConditional()
    conditional.configure(config, checkpoint)
    return conditional

  def evaluate(self):
    if EXPRESSION in self.configuration:
      expression = self.configuration[EXPRESSION]
      exp_vals = {}
      for condition in self.conditions:
        exp_vals[condition[ID]] = condition[CONDITION].evaluate()
      return evaluate_expression(expression, exp_vals)
    else:
      for condition in self.conditions:
        if not condition[CONDITION].evaluate():
          return False
      return True

  def get_new_checkpoint(self):
    new_checkpoint = {}
    for condition in self.conditions:
      new_checkpoint[condition[ID]] = condition[CONDITION].create_checkpoint()
    return new_checkpoint


def initialize_hooks(prehooks, posthooks):
  prehook_executors = []
  posthook_executors = []
  posthook_success_executors = []
  posthook_failure_executors = []
  for prehook_config in prehooks:
    executor = Executor()
    executor.configure(prehook_config)
    prehook_executors.append(executor)
  for posthook_config in posthooks:
    executor = Executor()
    executor.configure(posthook_config)
    if CONDITION in posthook_config:
      condition = posthook_config[CONDITION].lower()
      if condition == ALWAYS:
        posthook_executors.append(executor)
      elif condition == FAILURE:
        posthook_failure_executors.append(executor)
      elif condition == SUCCESS:
        posthook_success_executors.append(executor)
      else:
        raise ConfigError('Invalid execution condition specified')
    else:
      posthook_executors.append(executor)
  return prehook_executors, posthook_executors, \
         posthook_success_executors, posthook_failure_executors


def separate_hook_configs(hooks):
  global_hooks = []
  pipe_hooks = []
  for hook in hooks:
    if SCOPE in hook and hook[SCOPE].lower() == PIPE:
      pipe_hooks.append(hook)
    else:
      global_hooks.append(hook)
  return global_hooks, pipe_hooks


class PlumberPlanner:

  def __init__(self, config):
    self.config = config
    self.checkpoint_store = None
    self.pipes = None
    self.checkpoint_unit = 'single'
    if GLOBAL in config:
      if CHECKPOINTING in config[GLOBAL]:
        if UNIT in config[GLOBAL][CHECKPOINTING]:
          self.checkpoint_unit = config[GLOBAL][CHECKPOINTING][UNIT]
        self.checkpoint_store = create_checkpoint_store(
            config[GLOBAL][CHECKPOINTING])
      prehooks, prehooks_pipe = separate_hook_configs(
          get_or_default(config[GLOBAL], PREHOOK, []))
      posthooks, posthooks_pipe = separate_hook_configs(
          get_or_default(config[GLOBAL], POSTHOOK, []))
    self.prehooks, self.posthooks, self.posthooks_success, self.posthooks_failure = initialize_hooks(
        prehooks, posthooks)
    self.prehooks_pipe, self.posthooks_pipe, self.posthooks_pipe_success, self.posthooks_pipe_failure = initialize_hooks(
        prehooks_pipe, posthooks_pipe)
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

  def run_prehooks(self, pipe_scoped=False):
    if pipe_scoped:
      to_iterate = self.prehooks_pipe
      if len(to_iterate) > 0:
        LOG.info('Plumber: Executing global prehooks')
    else:
      to_iterate = self.prehooks
      if len(to_iterate) > 0:
        LOG.info('Plumber: Executing global prehooks')
    for hook in to_iterate:
      hook.execute()
      for result in hook.results:
        LOG.info(create_execution_log(result))

  def run_posthooks(self, pipe_scoped=False, last_result=None):
    if pipe_scoped:
      to_iterate = self.posthooks_pipe
      if len(to_iterate) > 0:
        LOG.info('Plumber: Executing global posthooks')
    else:
      to_iterate = self.posthooks
      if len(to_iterate) > 0:
        LOG.info('Plumber: Executing global posthooks')
    for hook in to_iterate:
      if CONDITION in hook.config and (
          hook.config[CONDITION] == last_result or hook.config[
        CONDITION] == ALWAYS):
        hook.execute()
        for result in hook.results:
          LOG.info(create_execution_log(result))

  def analyze(self):
    reports = []
    self.run_prehooks()
    for i in range(len(self.pipes)):
      self.run_prehooks(True)
      pending_execution = self.pipes[i].evaluate()
      reports.append(
          {ID: self.pipes[i].configuration[ID], DETECTED: pending_execution})
      self.run_posthooks(True)
    self.run_posthooks(True)

  def execute(self):
    new_checkpoint = {}
    error_occurred = None
    self.run_prehooks()
    for i in range(len(self.pipes)):
      self.run_prehooks(True)
      if self.pipes[i].evaluate():
        try:
          self.pipes[i].actions.execute()
          new_checkpoint[self.pipes[i].configuration[ID]] = self.pipes[
            i].get_new_checkpoint()
        except Exception as e:
          error_occurred = e
        if error_occurred is not None:
          self.run_posthooks(True, FAILURE)
          break
        else:
          self.run_posthooks(True, SUCCESS)
    if error_occurred is not None:
      self.run_posthooks(last_result=FAILURE)
      raise error_occurred
    else:
      self.run_posthooks(last_result=SUCCESS)
