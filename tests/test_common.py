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


def test_evaluate_expression():
  values = {'a': True, 'b': False}
  from plumber.common import evaluate_expression
  assert evaluate_expression('a and b', values) == False
  assert evaluate_expression('a or b', values) == True


def test_evaluate_expression_invalid():
  values = {'a': True, 'b': False}
  from plumber.common import evaluate_expression
  try:
    evaluate_expression('x and y', values)
    pytest.fail('Invalid expression should not succeeed')
  except Exception as e:
    assert type(e) is NameError
