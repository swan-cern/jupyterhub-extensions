# SWAN Spawner

Spawner for JupyterHub that enables configuring a session with CVMFS/LCG stacks, support for GPU, oAuth tokens, etc. 
If Binder is used to configure the Docker image used, it reverts to the default upstream configuration.
Works with both Docker and Kubernetes.

## Installation

```bash
pip3 install swanspawner
```

## Usage

Add to your JupyterHub config file

```python
c.JupyterHub.spawner_class = 'swanspawner.SwanDockerSpawner'
```

If you deploy with Docker, or

```python
c.JupyterHub.spawner_class = 'swanspawner.SwanKubeSpawner'
```

If you deploy with Kubernetes.

## Jupyter Notebook environment variables set during spawn

| env      |
|  ---     | 
| ROOT_LCG_VIEW_NAME   |
| ROOT_LCG_VIEW_PLATFORM   |
| USER_ENV_SCRIPT   |
| ROOT_LCG_VIEW_PATH   |
| USER  |
| USER_ID  |
| USER_GID  |
| HOME  |
| EOS_PATH_FORMAT  |
| SERVER_HOSTNAME  |
| MAX_MEMORY  |
| JPY_USER  |
| JPY_COOKIE_NAME  |
| JPY_BASE_URL  |
| JPY_HUB_PREFIX  |
| JPY_HUB_API_URL  |
| ACCESS_TOKEN  |
| OAUTH_INSPECTION_ENDPOINT  |

## Spawn Form configuration

To configure custom form, please set path to config file as below

```python
c.SwanSpawner.options_form_config = '<path>'
```

High level objects 

```yaml
optionsform:
  header: <options header text>
  enable_customenv_form: <boolean>
  enable_generate_url_form: <boolean>
  enable_network_form: <boolean>
  with_rucio: <array of rucio options objects>
  lcg_options: <array of lcg options objects>
  customenv_options: <array of customenvs options objects>
```

Options type label

```yaml
  lcg_options:
  - type: "label"
    label: 
      value: <id of label>,
      text: <displayed text of label>
  # ...
```

Options type selection

```yaml
  lcg_options:
  - type: "selection"
    lcg:
      value: <id of lcg>
      text: <displayed text of lcg>
    platforms:
      - value: <id of platform>
        text: <displayed text of platform>
      # ...
    cores:
      - value: <id of cores selection>
        text: <displayed text of cores selection>
      # ...
    memory:
      - value: <id of memory selection>
        text: <displayed text of memory selection>
      # ...
    clusters:
      - value: <id of cluster>
        text: <displayed text of cluster>
      # ...
  # ...
  customenv_options:
  - type: "selection"
    builder:
      value: <id of builder>
      text: <displayed text of builder>
    cores:
      - value: <id of cores selection>
        text: <displayed text of cores selection>
      # ...
    memory:
      - value: <id of memory selection>
        text: <displayed text of memory selection>
      # ...
    clusters:
      - value: <id of cluster>
        text: <displayed text of cluster>
      # ...
  # ...
```
An example yaml file can be seen in [options_form_config.yaml]()

## Mount options

To mount EOS or CVMFS with SwanDockerSpawner (which requires a mount with propagation "shared"), a new configuration was introduced by upstream:

```python
c.SwanSpawner.mounts = [
    {
        'source': '/eos',
        'target': '/eos',
        'type': 'bind',
        'propagation': 'shared'
    },
    {
        'source': '/cvmfs',
        'target': '/cvmfs',
        'type': 'bind',
        'propagation': 'shared'
    }
]
```