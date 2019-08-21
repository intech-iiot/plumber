from plumber.common import get_or_default, ConfigError, STATUS, ID, EXECUTED, \
  DETECTED
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
  assert evaluate_expression('a and b', values) is False
  assert evaluate_expression('a or b', values) is True


def test_evaluate_expression_invalid():
  values = {'a': True, 'b': False}
  from plumber.common import evaluate_expression
  try:
    evaluate_expression('x and y', values)
    pytest.fail('Invalid expression should not succeeed')
  except Exception as e:
    assert type(e) is NameError


def test_create_execution_report():
  results = [{ID: 'job', STATUS: EXECUTED}]
  from plumber.common import create_execution_report
  report = create_execution_report(results)
  assert 'job' in report
  assert EXECUTED in report


def test_create_execution_report_gitmoji():
  results = [{ID: 'job', STATUS: EXECUTED}]
  from plumber.common import create_execution_report, GITMOJI
  report = create_execution_report(results, True)
  assert 'job' in report
  assert GITMOJI[EXECUTED] in report


def test_create_initial_report():
  results = [{ID: 'job', DETECTED: True}]
  from plumber.common import create_initial_report
  report = create_initial_report(results)
  assert 'job' in report
  assert 'True' in report
