# Author: Diogo Castro 2019
# Copyright CERN


import os
import json
from tornado import web
from tornado.ioloop import IOLoop
from jupyterhub.services.auth import HubOAuthenticated, HubOAuthCallbackHandler
from kubernetes import client,config


class SwanNotificationsService(HubOAuthenticated, web.RequestHandler):
    """
        Render the user's notifications in JSON.
        Used by Jupyter extension SwanNotifications to display the messages in the interface.
    """

    def initialize(self, notifications_file, maintenance_file):
        self.notifications_file = notifications_file
        config.load_incluster_config()
        self.v1 = client.CoreV1Api()
        self.namespace = open("/var/run/secrets/kubernetes.io/serviceaccount/namespace").read()

    def check_node_schedulable(self,username):
        user_pod = self.v1.read_namespaced_pod(f'jupyter-{username}', self.namespace)
        user_node = user_pod.spec.node_name

        return self.v1.read_node(user_node).spec.unschedulable

    @web.authenticated
    async def get(self):

        response = []

        user = self.get_current_user()

        username= user['name']

        is_node_unschedulable= await IOLoop.current().run_in_executor(None, self.check_node_schedulable, username)

        if is_node_unschedulable:
           response.append({
               'id': 'maintenance_notice',
               'level': 'notice',
               'dismissible': 0,
               'message': 'This machine is scheduled for maintenance. Please finish your session, at your earliest convenience,'
                          ' and visit swan.cern.ch to open a new one.<br>'
           })


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
