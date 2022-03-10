import os, argparse
import tornado.ioloop
import tornado.web
from jupyterhub.utils import url_path_join
from jupyterhub.services.auth import HubOAuthCallbackHandler
from .service import SwanNotificationsService


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument('--port', default=8888, type=int, action="store", dest="port")
    parser.add_argument('--notifications_file', default="/srv/jupyterhub/notifications.json", action="store", 
                            dest="notification")
    parser.add_argument('--maintenance_file', default="/etc/nologin", action="store", dest="maintenance")
    parser.add_argument('--prefix', default="/", action="store", dest="prefix")
    args = parser.parse_args()

    prefix = os.environ.get('JUPYTERHUB_SERVICE_PREFIX', args.prefix)

    app = tornado.web.Application([
            (prefix, SwanNotificationsService,
                {'notifications_file': args.notification, 'maintenance_file': args.maintenance}),
            (url_path_join(prefix,"oauth_callback"),HubOAuthCallbackHandler),
            ],
            cookie_secret=os.urandom(32))
    app.listen(args.port)
    tornado.ioloop.IOLoop.current().start()
