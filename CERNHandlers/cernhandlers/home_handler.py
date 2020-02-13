# Author: Danilo Piparo 2016
# Copyright CERN

"""CERN Home handler"""

import os

from tornado import web, gen

from jupyterhub.handlers.base import BaseHandler
from jupyterhub.utils import url_path_join

class HomeHandler(BaseHandler):
    """Render the user's home page."""

    @web.authenticated
    async def get(self):
        user = self.current_user

        if user.running:
            # trigger poll_and_notify event in case of a server that died
            await user.spawner.poll_and_notify()

        # send the user to /spawn if they have no active servers,
        # to establish that this is an explicit spawn request rather
        # than an implicit one, which can be caused by any link to `/user/:name(/:server_name)`
        if user.active:
            url = url_path_join(self.base_url, 'user', user.escaped_name)
        else:
            url = url_path_join(self.hub.base_url, 'spawn', user.escaped_name)
        
        the_projurl = self.get_argument('projurl','')
        if the_projurl:
            url += '?projurl=%s' % the_projurl
        
        # Automatically redirect the user to the container or to spawner if 
        # he's not trying to shutdown the session. If multiple servers are allowed,
        # this cannot be done since we don't know to which to redirect.
        changeconfig = 'changeconfig' in self.request.query_arguments
        if not self.allow_named_servers and not changeconfig:
            self.redirect(url)
            return

        auth_state = await user.get_auth_state()
        html = self.render_template(
            'home.html',
            auth_state=auth_state,
            user=user,
            url=url,
            allow_named_servers=self.allow_named_servers,
            named_server_limit_per_user=self.named_server_limit_per_user,
            url_path_join=url_path_join,
            # can't use user.spawners because the stop method of User pops named servers from user.spawners when they're stopped
            spawners=user.orm_user._orm_spawners,
            default_server=user.spawner,
        )
        self.finish(html)