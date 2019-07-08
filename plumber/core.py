from plumber.interfaces import Conditional
from git import Repo
from plumber.common import current_path, LOG
import re

DIFF = 'diff'
PATH_SINGLE = 'path'
BRANCH = 'branch'
ACTIVE = 'active'
TARGET = 'target'
COMMIT = 'commit'
REQUIRED = 'required'
UTF8 = 'utf-8'


class LocalDiffConditional(Conditional):

  def __init__(self):
    self.target_diffs = None
    self.active_branch = None
    self.target_branch = None
    self.repo = None
    self.checkpoint = None

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

  def evaluate(self):
    if self.active_branch is not None and str(
        self.repo.active_branch) != self.active_branch:
      return False

  def create_checkpoint(self):
    pass

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

  def has_diff(self):
    if COMMIT not in self.checkpoint:
      return True
    detected_diffs = self._get_diffs_from_current()



class ShellConditional(Conditional):

  def __init__(self):
    pass

  def configure(self, config, checkpoint):
    pass

  def create_checkpoint(self):
    pass

  def evaluate(self):
    pass
