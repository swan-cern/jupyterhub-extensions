# Author: Diogo Castro 2019
# Copyright CERN


import os
import json
from tornado import web
from jupyterhub.services.auth import HubAuthenticated


class SwanNotificationsService(HubAuthenticated, web.RequestHandler):
    """
        Render the user's notifications in JSON.
        Used by Jupyter extension SwanNotifications to display the messages in the interface.
    """

    def initialize(self, notifications_file, maintenance_file):
        self.notifications_file = notifications_file
        self.maintenance_file = maintenance_file

    @web.authenticated
    def get(self):

        response = []

        if os.path.isfile(self.maintenance_file):
            with open(self.maintenance_file, 'r') as maintenance:
                response.append({
                    'id': 'maintenance_notice',
                    'level': 'notice',
                    'dismissible': 0,
                    'message': 'This machine is scheduled for maintenance. Please finish your session, at your earliest convenience,'
                               ' and visit swan.cern.ch to open a new one.<br>' + maintenance.read().replace('\n', '<br>')
                })

        user = self.current_user['name']

        notifications = {}
        if os.path.isfile(self.notifications_file):
            with open(self.notifications_file, 'r') as data_file:
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