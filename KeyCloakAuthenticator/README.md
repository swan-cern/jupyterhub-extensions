# KeyCloakAuthenticator

Authenticates users via SSO using OIDC. 

This authenticator implements a refresh mechanism, ensuring that the tokens stored in the user dict are always up-to-date (if the update is not possible, it forces a re-authentication of the user). It also allows exchanging the user token for tokens that can be used to authenticate against other (external) services.

This Authenticator is built on top of [OAuthenticator](https://github.com/jupyterhub/oauthenticator) and should be possible to use some of its configuration values.


## Requirements

* Jupyterhub
* oauthenticator
* PyJWT[crypto]
* openssl\_devel (see below)

## Installation

```bash
pip install keycloakauthenticator
```

If you enable check\_signature, you also need the `openssl_devel` (or equivalent in your distribution) package.

## Usage

In your JupyterHub config file, set the authenticator and configure it:

```python
# Enable the authenticator
c.JupyterHub.authenticator_class = 'keycloakauthenticator.KeyCloakAuthenticator'
c.KeyCloakAuthenticator.username_claim = 'preferred_username'

# URL to redirect to after logout is complete with auth provider.
c.KeyCloakAuthenticator.logout_redirect_url = 'https://cern.ch/swan'
c.KeyCloakAuthenticator.oauth_callback_url = 'https://swan.cern.ch/hub/oauth_callback'

# Specify the issuer url, to get all the endpoints automatically from .well-known/openid-configuration
c.KeyCloakAuthenticator.oidc_issuer = 'https://auth.cern.ch/auth/realms/cern'

# If you need to set a different scope, like adding the offline option for longer lived refresh token
c.KeyCloakAuthenticator.scope = ['profile', 'email', 'offline_access']
# Only allow users with this specific roles (none, to allow all)
c.KeyCloakAuthenticator.allowed_roles = []
# Specify the role to set a user as admin
c.KeyCloakAuthenticator.admin_role = 'swan-admin'

# If you have the roles in a non default place inside the user token, you can retrieve them
# This must return a set
def claim_roles_key(env, token):
    return set(token.get('app_roles', []))
c.KeyCloakAuthenticator.claim_roles_key = claim_roles_key

# Request access tokens for other services by passing their id's (this uses the token exchange mechanism)
c.KeyCloakAuthenticator.exchange_tokens = ['eos-service', 'cernbox-service']

# If your authenticator needs extra configurations, set them in the pre-spawn hook
def pre_spawn_hook(authenticator, spawner, auth_state):
    spawner.environment['ACCESS_TOKEN'] = auth_state['exchanged_tokens']['eos-service']
    spawner.environment['OAUTH_INSPECTION_ENDPOINT'] = authenticator.userdata_url.replace('https://', '')
    spawner.user_uid = auth_state['oauth_user']['cern_uid']
    decoded_token = authenticator._decode_token(auth_state['access_token'])
    spawner.user_roles = authenticator.claim_roles_key(authenticator, decoded_token)
c.KeyCloakAuthenticator.pre_spawn_hook = pre_spawn_hook

#Configure token signature verification
c.KeyCloakAuthenticator.check_signature=True
c.KeyCloakAuthenticator.jwt_signing_algorithms = ["HS256", "RS256"]

# Once a token is refreshed, by default jupyterhub does not trigger a refresh again (triggered when receiving any authenticated request) in `Authenticator.auth_refresh_age` seconds (default 5 minutes)
# If you want to refresh the token less often, and align the refresh to your tokens expiration, which will also trigger the update of the oAuth/OIDC token, this value can be changed:
c.KeyCloakAuthenticator.auth_refresh_age = 900 # 15 minutes
```


It's also necessary to configure the Client ID and secret. One way of doing this is by setting the following environment variables:

```bash
OAUTH_CLIENT_ID=my_id
OAUTH_CLIENT_SECRET=my_secret
```
