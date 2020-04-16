# KeyCloakAuthenticator

Authenticates users via SSO

## Installation

First, install dependencies:

    pip3 install -r requirements.txt

Then, install the package:

    python3 setup.py install

## Usage

Add to your JupyterHub config file

    c.JupyterHub.authenticator_class = 'keycloakauthenticator.KeyCloakAuthenticator'
