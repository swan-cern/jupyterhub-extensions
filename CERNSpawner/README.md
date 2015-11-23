# CERN Spawner

Obtains credentials for the user and spawns a container for her.

## Installation

First, install dependencies:

    pip3 install -r requirements.txt

Then, install the package:

    python3 setup.py install

## Usage

Add to your JupyterHub config file

    c.JupyterHub.spawner_class = 'cernspawner.CERNSpawner'
