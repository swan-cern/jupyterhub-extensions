# SwanCuller

JupyterHub services that checks and cleans user sessions.

## Requirements

This module requires and installs Tornado.

## Installation

Install the package:

```bash
pip install swanculler
```

## `swanblockedusersculler` service usage

`swanblockedusersculler` is a JupyterHub service that checks and delete user sessions for blocked users.

Call the binary and specify configuration parameters:
```bash
swanblockedusersculler --auth_check_interval=600 --authz_api_url ... --audience ... --auth-url ...
```

Configuration parameters:
* url: The JupyterHub API URL (default=$JUPYTERHUB_API_URL)
* auth_check_interval: The interval (in seconds) for checking for blocked users (default=14400)
* concurrency: Limit the number of concurrent requests made to the Hub (default=10)
* audience: Audience for CERN access token
* authz_api_url: URL to fetch user identity from authorization service
* auth_url: URL to fetch CERN access token
* auth_client_id: Client ID for blocked user check (default=$AUTH_CLIENT_ID)
* auth_client_secret: Client secret for blocked user check (default=$AUTH_CLIENT_SECRET)
