# PassThroughAuthenticator

Authenticates users with their username only

## Installation

First, install dependencies:

    pip3 install -r requirements.txt

Then, install the package:

    python3 setup.py install

## Usage

Add to your JupyterHub config file

    root = os.environ.get('PASSTHROUGHAUTH_DIR')
    sys.path.insert(0, root)
    c.JupyterHub.authenticator_class = 'passthroughauthenticator.PassThroughAuthenticator'
