from abc import ABCMeta, abstractmethod


class DataStore:
  __metaclass__ = ABCMeta
  store_type = None

  @abstractmethod
  def configure(self, config):
    pass

  @abstractmethod
  def get_data(self):
    pass

  @abstractmethod
  def save_data(self, content):
    pass


class Conditional:
  __metaclass__ = ABCMeta
  conditional_type = None

  @abstractmethod
  def evaluate(self):
    pass

  @abstractmethod
  def create_checkpoint(self):
    pass

  @abstractmethod
  def configure(self, config, checkpoint):
    pass
