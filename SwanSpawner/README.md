# SWAN Spawner

Obtains credentials for the user and spawns a container for her.

## Installation

First, install dependencies:

    pip3 install .

## Usage

Add to your JupyterHub config file

    c.JupyterHub.spawner_class = 'swanspawner.SwanDockerSpawner'

If you deploy with Docker, or

    c.JupyterHub.spawner_class = 'swanspawner.SwanKubeSpawner'

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

## Spawn Form configuration

To configure custom form, please set path to config file as below

    c.SwanSpawner.options_form_config = '<path>'
  
High level objects 

```
{
 "header: <options header text>
 "options": <array of options objects>
...
}
```

Options type label

```
{
 "options": [
    {
      "type": "label",
      "label": {
        "value": <id of label>,
        "text": <displayed text of label>
      }
    },
    ...
]
...
}
```

Options type selection

```
{
 "options": [
    {
      "type": "selection",
      "lcg": {
        "value": <id of lcg>,
        "text": <displayed text of lcg>
      },
      "platforms": [
        {
            "value": <id of platform>,
            "text": <displayed text of platform>
        }
        ...
      ],
      "cores": [
        {
            "value": <id of cores selection>,
            "text": <displayed text of cores selection>
        }
        ...
      ],
      "memory": [
        {
            "value": <id of memory selection>,
            "text": <displayed text of memory selection>
        }
        ...
      ],
      "clusters": [
        {
            "value": <id of cluster>,
            "text": <displayed text of cluster>
        }
        ...
      ]
    },
    ...
]
...
}
```
