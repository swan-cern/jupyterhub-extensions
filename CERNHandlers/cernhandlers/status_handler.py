# Author: Diogo Castro 2017
# Copyright CERN

"""CERN Status handler"""

import os
import json
from tornado import web
from jupyterhub.handlers.base import BaseHandler

maintenance_file = '/etc/iss.nologin'
notifications_file = '/srv/jupyterhub/notifications.json'

class StatusHandler(BaseHandler):
    """
        Render the user's notifications in JSON.
        Used by Jupyter extension SwanNotifications to display the messages in the interface.
    """

    @web.authenticated
    def get(self):

        response = []

        if os.path.isfile(maintenance_file):
            with open(maintenance_file, 'r') as maintenance:
                response.append({
                    'id': 'maintenance_notice',
                    'level': 'notice',
                    'dismissible': 0,
                    'message': 'This machine is scheduled for maintenance. Please finish your session, at your earliest convenience,'
                               ' and visit swan.cern.ch to open a new one.<br>' + maintenance.read().replace('\n', '<br>')
                })

        user = self.get_current_user().name

        notifications = {}
        if os.path.isfile(notifications_file):
            with open(notifications_file, 'r') as data_file:
                notifications = json.load(data_file)

        for notification in notifications:
            if notification['user'] == '*' or user in notification['user']:
                new_notification = {}
                new_notification['id'] = notification['id']
                new_notification['level'] = notification['level']
                new_notification['dismissible'] = notification['dismissible']
                new_notification['message'] = notification['message']
                response.append(new_notification)

        self.write(json.dumps(response, ensure_ascii=False))
