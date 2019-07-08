from setuptools import setup, find_packages

setup(
    name="plumber",
    version='0.0.1a',
    description='A CD/CI tool that executes arbitrary commands upon detection of change between the current commit and the last checkpoint',
    author='Usman Shahid',
    author_email='usman.shahid@intechww.com',
    packages=find_packages(),
    install_requires=[
      'Click==7.0',
      'gitpython==2.1.11',
      'PyYAML==5.1.1',
      'kubernetes== 10.0.0'
    ]
)
