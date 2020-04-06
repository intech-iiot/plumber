import yaml

from plumber.common import LOG, evaluate_expression, ConfigError, \
  ExecutionFailure, EXPRESSION, ID, ACTIONS, TYPE, \
  LOCALDIFF, GLOBAL, CHECKPOINTING, UNIT, CONDITIONS, CONDITION, ALWAYS, \
  FAILURE, SUCCESS, PREHOOK, POSTHOOK, PIPES, get_or_default, \
  DETECTED, SINGLE, STATUS, UNKNOWN, EXECUTED, \
  NOT_DETECTED, PIPE, FAILED, PLUMBER_LOGS, create_execution_report, \
  wrap_in_dividers
from plumber.io import create_checkpoint_store
from plumber.operators import Executor, LocalDiffConditional


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
    if self.conditions is None:
      return True
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
    if self.conditions is None:
      return None
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
    self.posthooks_execute = False
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
    if self.posthooks_execute and (self.posthooks is not None or (
        last_result == SUCCESS and self.posthooks_success is not None) or (
        last_result == FAILURE and self.posthooks_failure is not None)):
      LOG.log(PLUMBER_LOGS,
              wrap_in_dividers("Running global posthooks",
                               divider_char='-'))
      super(PlumberPlanner, self).run_posthooks(last_result)

  def get_analysis_report(self):
    if self.pipes is None:
      raise ExecutionFailure('No pipes configured')

    def get_report():
      return [
        {ID: pipe.config[ID], DETECTED: pipe.wrap_in_hooks(pipe.evaluate)()}
        for pipe in self.pipes]

    return self.wrap_in_hooks(get_report)()

  def init_checkpoint(self, force=False):
    new_checkpoint = {}
    if len(self.current_checkpoint) != 0 and not force:
      raise ExecutionFailure('A checkpoint already exists')
    if self.pipes is None:
      raise ExecutionFailure('No pipes configured')
    for pipe in self.pipes:
      checkpoint = pipe.get_new_checkpoint()
      if checkpoint is not None:
        new_checkpoint[pipe.config[ID]] = checkpoint
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
      if self.pipes is None:
        raise ExecutionFailure('No pipes configured')
      self.results = [{ID: pipe.config[ID], STATUS: UNKNOWN, PIPE: pipe} for
                      pipe in self.pipes]
      for item in self.results:
        LOG.log(PLUMBER_LOGS, wrap_in_dividers(
            'Pipe evaluation for [{}]'.format(item[ID])))

        def pipe_execution_logic():
          if item[PIPE].evaluate():
            self.posthooks_execute = True
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
            checkpoint = item[PIPE].get_new_checkpoint()
            if checkpoint is not None:
              self.current_checkpoint[item[PIPE].config[ID]] = checkpoint

        try:
          item[PIPE].wrap_in_hooks(pipe_execution_logic)()
        except Exception as e:
          item[STATUS] = FAILED
          raise e
      return self.results

    return self.wrap_in_hooks(main_execution_logic, save_new_checkpoint)()


def contains_activity(results):
  if results is None:
    return False
  for result in results:
    if result[STATUS] != NOT_DETECTED:
      return True
  return False


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
