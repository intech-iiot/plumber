from setuptools import setup, find_packages

setup(
    name="plumber",
    version='0.0.1b',
    description='A CD/CI tool that executes arbitrary commands upon detection of change between the current commit and the last checkpoint',
    author='Usman Shahid',
    author_email='usman.shahid@intechww.com',
    packages=find_packages(),
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
      'gitpython==2.1.11',
      'PyYAML==5.1.1',
      'kubernetes== 10.0.0'
    ]
)
