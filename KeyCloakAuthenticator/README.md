# KeyCloakAuthenticator

Authenticates users via SSO using OIDC


## Requirements

* Jupyterhub
* oauthenticator
* PyJWT

## Installation

```bash
pip install keycloakauthenticator
```

## Usage

In your JupyterHub config file, set the authenticator and configure it:

```python
# Enable the authenticator
c.JupyterHub.authenticator_class = 'keycloakauthenticator.KeyCloakAuthenticator'
c.KeyCloakAuthenticator.enable_auth_state = True
c.KeyCloakAuthenticator.username_key = 'preferred_username'
c.KeyCloakAuthenticator.logout_redirect_uri = 'https://cern.ch/swan'
c.KeyCloakAuthenticator.oauth_callback_url = 'https://swan.cern.ch/hub/oauth_callback'

# Retrieve the user uid from the token
def get_uid_hook(spawner, auth_state):
    spawner.user_uid = auth_state['oauth_user']['cern_uid']
c.KeyCloakAuthenticator.get_uid_hook = get_uid_hook

# Specify the issuer url, to get all the endpoints automatically from .well-known/openid-configuration
c.KeyCloakAuthenticator.oidc_issuer = 'https://auth.cern.ch/auth/realms/cern'

# Only allow users with this specific roles (none, to allow all)
c.KeyCloakAuthenticator.accepted_roles = set()
# Specify the role to set a user as admin
c.KeyCloakAuthenticator.admin_role = 'swan-admin'
```

It's also necessary to configure the Client ID and secret. One way of doing this is by setting the following environment variables:

```bash
OAUTH_CLIENT_ID=my_id
OAUTH_CLIENT_SECRET=my_secret
```