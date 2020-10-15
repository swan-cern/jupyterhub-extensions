# SwanHub

JupyterHub wrapper that automatically configures the SWAN templates and handlers.

These handlers replace the default ones with slightly modified versions (for example, the user info api endpoint provides information about the auth state, which is hidden in the default implementation).

## Requirements

This module requires and installs JupyterHub.

## Installation

Install the package

```bash
pip install swanhub
```

To have the proper css, it is necessary to download a release from https://github.com/swan-cern/common into the folder `/usr/local/share/jupyterhub/static/swan/`.

## Usage

Start SwanHub as you would for JupyterHub, and with the same configurations. Example:

```bash
swanhub --config /path/to/my/jupyterhub_config.py
```