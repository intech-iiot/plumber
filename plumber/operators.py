import re
import subprocess

import yaml
from git import Repo

from plumber.common import current_path, LOG, evaluate_expression, ConfigError, \
  ExecutionFailure, DIFF, BRANCH, ACTIVE, TARGET, EXPRESSION, COMMIT, ID, PATH, \
  STEPS, BATCH, TIMEOUT, RETURN_CODE, STEP, STDOUT, STDERR, get_or_default, \
  create_execution_log, UTF8, PLUMBER_LOGS, CONTENT
from plumber.interfaces import Conditional

ON_FAILURE_SCRIPT = "touch failed"


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
    found_diffs = list()
    commit_found = False
    for commit in self.repo.iter_commits():
      diffs = self.repo.head.commit.diff(commit)
      for diff in diffs:
        found_diffs.append(diff)
      commit_found = str(commit) == self.checkpoint[COMMIT]
      if commit_found:
        break
    if not commit_found:
      LOG.warn(
          '[{}] traversed all git log, checkpoint commit not found'.format(
              self.id))
    LOG.info(
        '[{}] detected diffs since last run:\n{}\n'.format(self.id, ''.join(
            f'\n\t {l.a_rawpath.decode(UTF8)}' for l in found_diffs)))
    return found_diffs

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

  def _has_content_diff(self, pattern, diff):
    diff_lines = set(
        diff.a_blob.data_stream.read().decode(UTF8).split('\n')).difference(
        set(diff.b_blob.data_stream.read().decode(UTF8).split('\n')))
    for item in diff_lines:
      if re.match(pattern, item):
        return True
    return False

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
            if re.match(target_diff[PATH],
                        detected_diff.a_rawpath.decode(UTF8)):
              LOG.info('[{}] path pattern {} matches {}'.format(self.id,
                                                                target_diff[
                                                                  PATH],
                                                                detected_diff.a_rawpath.decode(
                                                                    UTF8)))
              content = get_or_default(target_diff, CONTENT, None, str)
              if content is not None:
                if id not in exp_dict or not exp_dict[id]:
                  exp_dict[id] = self._has_content_diff(content, detected_diff)
              else:
                exp_dict[id] = True
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
          if re.match(path, detected_diff.a_rawpath.decode(UTF8)):
            LOG.info('[{}] path pattern {} matches {}'.format(self.id, path,
                                                              detected_diff.a_rawpath.decode(
                                                                  UTF8)))
            content = get_or_default(target_diff, CONTENT, None, str)
            if content is not None:
              if self._has_content_diff(content, detected_diff):
                return True
            else:
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
          self._run_script(script=ON_FAILURE_SCRIPT)
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
            self._run_script(script=ON_FAILURE_SCRIPT)
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
