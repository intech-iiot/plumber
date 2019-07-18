from setuptools import setup, find_packages

setup(
    name="plumber",
    version='0.0.1a',
    description='A CD/CI tool that executes arbitrary commands upon detection of change between the current commit and the last checkpoint',
    author='Usman Shahid',
    author_email='usman.shahid@intechww.com',
    packages=find_packages(),
    entry_points={
      'console_scripts': [
        'plumber=plumber.cli:cli'
      ]
    },
    install_requires=[
      'Click==7.0',
      'click-log==0.3.2',
      'terminaltables==3.1.0',
      'gitpython==2.1.11',
      'PyYAML==5.1.1',
      'kubernetes== 10.0.0'
    ]
)
