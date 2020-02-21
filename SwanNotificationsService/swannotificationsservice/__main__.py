import os, argparse
import tornado.ioloop
import tornado.web
from .service import SwanNotificationsService


if __name__ == "__main__":

    parser = argparse.ArgumentParser()
    parser.add_argument('--port', default=8888, type=int, action="store", dest="port")
    parser.add_argument('--notifications_file', default="/srv/jupyterhub/notifications.json", action="store", 
                            dest="notification")
    parser.add_argument('--maintenance_file', default="/etc/nologin", action="store", dest="maintenance")
    parser.add_argument('--prefix', default="/", action="store", dest="prefix")
    args = parser.parse_args()

    prefix = os.environ.get('JUPYTERHUB_SERVICE_PREFIX', args.prefix)

    app = tornado.web.Application([(prefix, SwanNotificationsService, 
                    {'notifications_file': args.notification, 'maintenance_file': args.maintenance})])
    app.listen(args.port)
    tornado.ioloop.IOLoop.current().start()