# KeyCloakAuthenticator

Authenticates users via SSO using OIDC. 

This authenticator implements a refresh mechanism, ensuring that the tokens stored in the user dict are always up-to-date (if the update is not possible, it forces a re-authentication of the user). It also allows exchanging the user token for tokens that can be used to authenticate against other (external) services.


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
# Exchange the token for tokens usable on other services (pass the audience/app id of the other services)
c.KeyCloakAuthenticator.exchange_tokens = ['eos-service', 'cernbox-service']
```

It's also necessary to configure the Client ID and secret. One way of doing this is by setting the following environment variables:

```bash
OAUTH_CLIENT_ID=my_id
OAUTH_CLIENT_SECRET=my_secret
```