# SWAN Spawner

Obtains credentials for the user and spawns a container for her.

## Installation

First, install dependencies:

    pip3 install .

## Usage

Add to your JupyterHub config file

    c.JupyterHub.spawner_class = 'swanspawner.SwanDockerSpawner'

If you deploy with Docker, or

    c.JupyterHub.spawner_class = 'swanspawner.SwanKukeSpawner'

If you deploy with Kubernetes.
