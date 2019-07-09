from git import Repo
import re

from plumber.common import current_path, LOG
from plumber.interfaces import Conditional

DIFF = 'diff'
PATH_SINGLE = 'path'
BRANCH = 'branch'
ACTIVE = 'active'
TARGET = 'target'
COMMIT = 'commit'
REQUIRED = 'required'
EXPRESSION = 'expression'
UTF8 = 'utf-8'
LABEL = 'label'


class LocalDiffConditional(Conditional):

  def __init__(self):
    self.target_diffs = None
    self.active_branch = None
    self.target_branch = None
    self.repo = None
    self.checkpoint = None
    self.expression = None

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
    if self.active_branch is not None and str(
        self.repo.active_branch) != self.active_branch:
      return False
    if self.target_branch is not None and str(
        self.repo.active_branch) != self.target_branch:
      previous_branch = str(self.repo.active_branch)
      try:
        self.repo.git.checkout(self.target_branch)
        return self._has_diff()
      finally:
        self.repo.git.checkout(previous_branch)
    else:
      return self._has_diff()

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
    for target_diff in self.target_diffs:
      if LABEL in target_diff:
        for detected_diff in diffs:
          if PATH_SINGLE in target_diff:
            if re.match(target_diff[PATH_SINGLE], detected_diff.a_rawpath):
              exec('{} = True'.format(target_diff[LABEL]))
            else:
              exec('{} = False'.format(target_diff[LABEL]))
    return eval(self.expression)

  def _has_diff_all(self):
    diffs = self._get_diffs_from_current()
    for target_diff in self.target_diffs:
      for detected_diff in diffs:
        if PATH_SINGLE in target_diff:
          if re.match(target_diff[PATH_SINGLE], detected_diff.a_rawpath):
            return True


class ShellConditional(Conditional):

  def __init__(self):
    pass

  def configure(self, config, checkpoint):
    pass

  def create_checkpoint(self):
    pass

  def evaluate(self):
    pass
