from setuptools import setup, find_packages
import os, json


def load_version():
  with open(
      os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   'dove.json'), 'r') as data:
    return json.load(data)['version']


setup(
    name="plumber",
    version=load_version(),
    description='A CD/CI tool that executes arbitrary commands upon detection of change between the current commit and the last checkpoint',
    author='Usman Shahid',
    author_email='usman.shahid@intechww.com',
    packages=find_packages(),
    include_package_data=True,
    entry_points={
      'console_scripts': [
        'plumber=plumber.cli:cli'
      ]
    },
    tests_require=[
      'mock==2.0.0',
      'pytest==4.3.1',
      'pytest-cov==2.7.1'
    ],
    setup_requires=["pytest-runner==4.4"],
    install_requires=[
      'Click==7.0',
      'click-log==0.3.2',
      'terminaltables==3.1.0',
      'pyfiglet==0.8.post1',
      'gitpython==3.1.0',
      'PyYAML==5.1.1',
      'kubernetes== 10.0.0'
    ]
)
