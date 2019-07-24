from plumber.common import get_or_default, ConfigError
import pytest


def test_get_or_default():
  mydict = {'key': 'value'}
  value = get_or_default(mydict, 'key', 'default')
  assert value == 'value'


def test_get_or_default_default():
  mydict = {}
  value = get_or_default(mydict, 'key', 'default')
  assert value == 'default'


def test_get_or_default_type_check():
  mydict = {'key': 'value'}
  value = get_or_default(mydict, 'key', 'default', str)
  assert value == 'value'


def test_get_or_default_type_check_fail():
  mydict = {'key': 'value'}
  try:
    get_or_default(mydict, 'key', 'default', int)
    pytest.fail('Should throw {}'.format(ConfigError))
  except Exception as e:
    assert type(e) is ConfigError
