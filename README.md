## JupyterHub extensions

Repository that stores all the JupyterHub extensions for SWAN.

* [KeyCloakAuthenticator](KeyCloakAuthenticator) - OIDC authenticator for SWAN, compatible with KeyCloak
* [SwanCuller](SwanCuller) - JupyterHub service that checks and cleans user sessions
* [SwanHub](SwanHub) - JupyterHub wrapper that automatically configures the SWAN templates and handlers
* [SwanNotificationsService](SwanNotificationsService) - JupyterHub service that exposes an API with notifications for the logged in user
* [SwanSpawner](SwanSpawner) - Spawner for JupyterHub that enables configuring a session with CVMFS/LCG stacks, support for GPU, oAuth tokens, etc

### Create a release

The creation of a new release in this repo is now automated. Just run the Github action "Release" manually, and specify the extension name and the increment type.

### Development

You can develop JupyterHub and the custom SWAN extensions locally by following
these steps:

#### Install dependencies

- Create a virtual enviroment and activate it:

```bash
uv venv
source .venv/bin/activate
```

- Install all the packages in editable mode:

```bash
uv pip install -e KeyCloakAuthenticator/
uv pip install -e SwanCuller/
uv pip install -e SwanHub/
uv pip install -e SwanNotificationsService/
uv pip install -e SwanSpawner/
```

- Install dev dependencies:

```bash
uv pip install --group dev
```

- Install jupyterlab:

```bash
uv pip install jupyterlab
```

#### Start the hub

- Disable cache in your devtools (FF/Chrome: Network tab -> Disable Cache)
- Create a development JupyterHub config in the repo root (see example below)
- Get the `options_form.yaml`:

You can get it from the [gitops repo](https://gitlab.cern.ch/swan/gitops).
You can use e.g. `swan-cern/prod/values_options_form.yaml` or
`swan-cern/qa/values_options_form.yaml`. We cannot use this file directly but
we first need to extract the `optionsform` key from it. You can use this Python
script to do so:

```python
# /// script
# requires-python = ">=3.8"
# dependencies = [
#   "pyyaml",
# ]
# ///
import yaml

values_options_form = '../gitops/swan-cern/qa/values_options_form.yaml'
with open(values_options_form) as f:
    data = yaml.safe_load(f)

optionsform = data['optionsform']

with open('options_form.yaml', 'w') as f:
    yaml.dump(optionsform, f)
```

- From the repo root run:

```bash
JUPYTERHUB_CRYPT_KEY=<32bytes> \
OAUTH_CLIENT_ID=swan-qa \
OAUTH_CLIENT_SECRET=<CLIENT_SECRET> \
swanhub -f jupyter_hub_config.py
```

You can get the `OAUTH_CLIENT_SECRET` from the Application portal for the `swan-qa` application.

#### Start the frontend assets watcher (from the repo root):

```bash
python watch.py
```

#### JupyterHub config for development

```python
import os


# Enable debug mode
# ================================================

os.environ['SWANHUB_ENV'] = 'dev'
c.Application.log_level = 'DEBUG'
c.Spawner.debug = True


# Auth configuration
# ================================================

c.JupyterHub.authenticator_class = 'keycloakauthenticator.auth.KeyCloakAuthenticator'
c.KeyCloakAuthenticator.username_claim = 'preferred_username'

# URL to redirect to after logout is complete with auth provider.
c.KeyCloakAuthenticator.logout_redirect_url = 'https://cern.ch/swan'
c.KeyCloakAuthenticator.oauth_callback_url = 'http://localhost:8000/hub/oauth_callback'

# Specify the issuer url, to get all the endpoints automatically from .well-known/openid-configuration
c.KeyCloakAuthenticator.oidc_issuer = 'https://auth.cern.ch/auth/realms/cern'

# If you need to set a different scope, like adding the offline option for longer lived refresh token
c.KeyCloakAuthenticator.scope = ['profile', 'email', 'offline_access', 'openid']
# Only allow users with this specific roles (none, to allow all)
c.KeyCloakAuthenticator.allowed_roles = []
# Specify the role to set a user as admin
c.KeyCloakAuthenticator.admin_role = 'swan-admins'


# Spawner configuration
# ================================================

# Use a custom local process spawner:
# TODO: Figure out how to use our user image with a docker spawner
c.JupyterHub.spawner_class = 'swanspawner.localswanspawner.LocalSwanSpawner'

# Set the path to the options form config
c.LocalSwanSpawner.options_form_config = 'options_form.yaml'


# Proxy configuration (Optional)
# ================================================

# Do not start a proxy automatically
# Start your own proxy with: `configurable-http-proxy --insecure`
# This makes it easy to inspect the proxy state (no auth required, you can directly query e.g. /api/routes)
# c.ConfigurableHTTPProxy.should_start = False
# c.ConfigurableHTTPProxy.auth_token = 'abcd'
```