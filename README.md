## JupyterHub extensions

Repository that stores all the JupyterHub extensions for SWAN.

* [KeyCloakAuthenticator](KeyCloakAuthenticator) - OIDC authenticator for SWAN, compatible with KeyCloak
* [SwanCuller](SwanCuller) - JupyterHub service that checks and cleans user sessions
* [SwanHub](SwanHub) - JupyterHub wrapper that automatically configures the SWAN templates and handlers
* [SwanNotificationsService](SwanNotificationsService) - JupyterHub service that exposes an API with notifications for the logged in user
* [SwanSpawner](SwanSpawner) - Spawner for JupyterHub that enables configuring a session with CVMFS/LCG stacks, support for GPU, oAuth tokens, etc

#### Create a release

The creation of a new release in this repo is now automated. Just run the Github action "Release" manually, and specify the extension name and the increment type.