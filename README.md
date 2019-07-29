# Plumber
Plumber is a CLI tool that provides the plumbing necessary for CD/CI pipelines. It allows you to execute shell scripts that you define only when certain conditions are fulfilled. These conditions can include detected changes at a user defined git path. The tool also creates checkpoints when it runs your scripts and changes something, and only checks for the validity of the conditions between subsequent checkpoints. The checkpoints can be stored on either a git repo or a kubernetes configmap.

## Quickstart

1. Just clone the repo and do a `pip install .`. This will install the CLI entrypoint on your environment. 
2. Create a new file `plumber.yml` inside the repository you want to run your CD on and add the following to it:

```yml
global:
  checkpointing:
    type: localgit

pipes:
  - id: my-cd
    conditions:
      - type: localdiff
        id: detect-path
        branch:
          active: live
        diff:
          - path: cd-test/.*
    actions:
      steps:
        - echo "Running my CD" > cd.log
```
This is the config file from which plumber picks it's configuration and work spec. The above file specifies:
* We want to store the plumber checkpoint in the same git repository. The default checkpoint file is `.plumber.checkpoint.yml`
* We want to detect if any git changes have been made on a path that matches the regex `cd-test/.*`
* If the tool detects a change, we want it to echo "Running my CD" to a file cd.log

3. Create the directory `cd-test` in your repo, add any file to it and commit the file
4. Run the command `plumber status`. This will print out the following:
```
+----+-------+-----------------+
| SN | ID    | CHANGE DETECTED |
+----+-------+-----------------+
| 1  | my-cd | True            |
+----+-------+-----------------+
```
5. Run the command `plumber go`. This will detect the change, run the actions, printing out a report at the end:
```
+----+-------+----------+
| SN | ID    | STATUS   |
+----+-------+----------+
| 1  | my-cd | executed |
+----+-------+----------+
```
6. Check the contents of the file `cd.log`. You'll find the line `Running my CD`
## Usage

After the installation, the tool should be accessible through shell. Do a `plumber --help` to see the capabilities of the tool:

```shell
Usage: plumber [OPTIONS] COMMAND [ARGS]...

  A CD/CI tool capable of running arbitrary shell scripts/commands when it
  detects certain configurable conditions to be true.

  Maintained by: Intech IIS

Options:
  --help  Show this message and exit.

Commands:
  go      Detect changes and run CD/CI steps
  init    Initiate a new checkpoint
  status  Detect changes and print out a report
```

Now do `plumber status --help`:
```shell
Usage: plumber status [OPTIONS]

  Detect changes and print out a report

Options:
  -c, --cfg TEXT  Path tho plumber config file
  -v, --verbose   Set the verbosity level
  --help          Show this message and exit.
```

### Configuration File

Plumber picks it's configuration from a YAML config file. The default for this file is `plumber.yml` located in the same directory where the tool is executed. The config file location can be overwritten with the `--cfg` flag provided in each subcommand.

#### Config Reference

The full configuration file has the following structure:

```yml
global:
  checkpointing:
    unit: single/pipe
    type: kubeconfig
    config:
      name: name-of-config
      namespace: name-of-namespace
#   type: localfile
#   config:
#     path: filepath
#   type: localgit
#   config:
#     path: filepath

  prehook:
    - batch: false
      timeout: 0
      steps:
        - command1
        - command2
  posthook:
    - condition: always/failure/success
      batch: false
      timeout: 0
      steps:
        - command1
        - command2

pipes:
  - id: Something
    prehook:
      - batch: false
        timeout: 0
        steps:
          - command1
          - command2
    posthook:
      - condition: always/failure/success
        batch: false
        timeout: 0
        steps:
          - command1
          - command2
    expression: paths and script
    conditions:
      - type: localdiff
        id: paths
        branch:
          active: master
          target: master
        expression: path1 and path2
        diff:
          - path: regex
            id: path1
          - path: regex
            id: path2
    actions:
      batch: false
      timeout: 0
      steps:
        - command1
        - command2
        - command3
```

#### Checkpointing

The tool supports three checkpoint stores:

##### 1. kubeconfig:

This stores the checkpoint in a kubernetes configuration map. The configuration is specified as follows:

```yml 
global:
  checkpointing:
    type: kubeconfig
    config:
      name: name-of-config
      namespace: name-of-namespace
```
The name and namespace are optional and default to `plumber-checkpoint` and `default`.
The tool uses the incluster config loading and requires proper RBAC setup for CRUD on ConfigMap resource. [More Info](https://github.com/kubernetes-client/python/blob/master/examples/in_cluster_config.py).

##### 2. localgit:

This stores the checkpoint in a file on a git repository. The configuration is specified as follows:

```yml
global:
  checkpointing:
    type: localgit
    config:
      path: path-to-checkpoint-file
```
The path is optional and defaults to `.plumber.checkpoint.yml` at the root of the git repo.
The credentials to push to the git repo can be provided through the standard git credentials methods. [More Info](https://git-scm.com/docs/gitcredentials)

##### 3. localfile: 

This stores the checkpoint in a local file. The configuration is specified as follows:

```yml
global:
  checkpointing:
    type: localfile
    config:
      path: filepath
```

The path is optional and defaults to `.plumber.checkpoint.yml`.


##### Checkpoint unit:

You can additionally specify the checkpoint unit to one of the following:
* single: The new checkpoint is only created when all of the CD jobs are successful
* pipe: The existing checkpoint is modified to contain the checkpoints of only the pipes that were successful

The configuration is specified as follows:

```yml
global:
  checkpointing:
    unit: single
```
The unit defaults to `single` if not specified.

#### Pipes

Pipes are the logical unit of CD. The interpretation of what a pipe is dependent on a user, it can be the deployment task of a service, or it can be the deployment task of a whole tech stack. Systematically, a pipe encapsulates a bunch of execution conditions and actions that are performed when those conditions are met. A pipe is identified by an id, which is a required field. The checkpoint file also contains individual checkpoints for each pipe. 

We define a pipe in the configuration as follows:

```yml
pipes:
  - id: pipe-id
    expression: paths and script
    conditions:
      - type: localdiff
        id: paths
        branch:
          active: master
          target: master
        expression: path1 and path2
        diff:
          - path: regex
            id: path1
          - path: regex
            id: path2
    actions:
      batch: false
      timeout: 0
      steps:
        - command1
        - command2
        - command3
```
The info on different fields is as follows:

**id:**
The required unique identifier for the pipe. It is used in checkpointing and reporting.

**conditions:**
A condition is something that is evaluated and based on it's result, the tool decides whether to perform the CD steps or not. The tool is aimed to support multiple conditional operators, right now it supports the following:

Condition | Description
----------|------------
localdiff | Detect diff changes on the local git repository between checkpoints

**expression:**
The expression is an optional field and can contain a valid python expression with ids of the conditions. If specified, the expression is evaluated and the pipe is only executed if the expression evaluation returns true. If not specified, the pipe is executed if any of the condition returns true.

**actions:**
Contains the shell executable scripts and commands that are executed if the pipe conditions/expression evaluation returns true. 
The `batch` option specifies whether the commands are batched in a single script upon execution. This forces the steps to be executed as a single step (in a single shell command).
You can specify a `timeout` in seconds on the steps. If a step (or all the steps in case `batch` is set to true) takes more time than the specified timeout, the execution is halted and the cd job fails.
Both of these options are optional.

#### Conditions:

The details of the supported conditions is as follows:

##### localdiff

The localdiff condition can detect changes on the git repository the tool is run on. The condition config is specified as follows:


```yml
pipes:
  - id: pipe-id
    conditions:
      - type: localdiff
        id: paths
        branch:
          active: master
          target: master
        expression: path1 and path2
        diff:
          - path: regex
            id: path1
          - path: regex
            id: path2
```
The info on different fields is as follows:

**id:**
The required unique identifier for the condition. It is used in checkpointing and reporting.

**branch.active:**
The condition is only evaluated if the branch specified here is checked out. Otherwise it evaluates to false. This is optional, and if not specified, the current branch is ignored and the condition is still evaluated.

**branch.target:**
The condition first checks out the branch specified here before evaluation. This is optional and if not specified, the branch is not changed before evaluation.

**diff:**
Contains a list of diff configurations, each with the following fields:

**diff[].path:**
A regular expression that can match a path in the git repo. The tool condition detects all the files that were changed since last checkpoint and then checks if any of those files match this expression. If it finds a match, the condition returns true.

**diff[].id:**
An identifier for the path, it is only required when the expression is specified

**expression:**
The expression is an optional field and can contain a valid python expression with ids of the paths. If specified, the expression is evaluated and the condition returns it's result. If not specified, the condition returns true if any of the path matches.

#### Hooks

The tool has the ability to run scripts or commands before and after the detection and execution of the CD steps. The steps that are executed before the pipes are prehooks while the ones that are executed after the pipes are posthooks.
Both types of hooks can be specified at global and pipe-local level. The posthooks can be conditioned i.e. the user can specify whether to always execute the posthooks or only execute them upon success or failure.
The global hooks are specified under the global settings as follows:

```yml
global:
  prehook:
    - batch: false
      timeout: 0
      steps:
        - command1
        - command2
  posthook:
    - condition: always/failure/success
      batch: false
      timeout: 0
      steps:
        - command1
        - command2
```
while the pipe-scoped hooks are specified within the pipe configuration:
```yml
pipes:
  - id: my-pipe
    prehook:
      - batch: false
        timeout: 0
        steps:
          - command1
          - command2
    posthook:
      - condition: always/failure/success
        batch: false
        timeout: 0
        steps:
          - command1
          - command2
```
The functionality of `batch` and `timeout` is the same as in pipes.
The `condition` on the `posthook` can have the following values:
* always: The posthook is always executed
* success: The posthook is only executed if the pipe is successful
* failure: The posthook is only executed if the pipe fails

It defaults to `always`.

#### Environment Variables Substitution

You can specify environment variables in the configuration file, the variable is replaced with it's respective value if found when reading the configuration. The format for specifying the environment variables is as follows:

```yml
global:
  checkpointing:
    unit: ${env.CHECKPOINT_UNIT}
```
If the `CHECKPOINT_UNIT` environment variable is defined, it's value is replaced with the above placeholder when reading the configuration.
Also note that this will not work if you stringify the placeholder:

```yml
global:
  checkpointing:
    unit: "${env.CHECKPOINT_UNIT}"
```

#### Logs/Verbosity

You can change the level of logs/verbosity through the `-v/--verbose` flag. For example, to print out the debug logs, run any command with the `-vvv` flag e.g.:

```
plumber go -vvv
```