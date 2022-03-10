# SwanNotificationsService

JupyterHub service that exposes an API with notifications for the logged in user.
The notifications are specified in a json file. If a "maintenance file" exists, a notification will be given that the service is under maintenance.

This extension works in conjunction with [SwanNotifications](https://github.com/swan-cern/jupyter-extensions/tree/master/SwanNotifications).

## Requirements

This module requires and installs JupyterHub.

## Installation

Install the package:

```bash
pip install swannotificationsservice
```

## Update the container image

This folder contains a Dockerfile that can be used to create an image for the pod that runs the notifications service. Once you release to PyPI you need to create a new image, e.g.

```bash
docker build -t gitlab-registry.cern.ch/swan/docker-images/jupyterhub/notifications:v0.1.0 && docker push gitlab-registry.cern.ch/swan/docker-images/jupyterhub/notifications:v0.1.0
```

## Usage

Call the binary and specify configuration parameters:
```bash
swannotificationsservice --notifications_file /srv/jupyterhub/notifications.json
```

Configuration parameters:

* port (default: 8888)
* notifications_file (default: /srv/jupyterhub/notifications.json)
* maintenance_file (default: /etc/nologin)
* prefix (default: /)

Notifications file example:

```json
[
    {
        "user": "*",
        "id": "notif1",
        "level": "info",
        "dismissible": 0,
        "message": "This is a notification"
    }
]
```

Explanation:
* user: username or '*' for all users;
* id: unique identifier;
* level: type of the notification (notice, info, success, or error)
* dismissible: wether the user will be able to permanently hide the notification (0 or 1)
* message: the text/html message
