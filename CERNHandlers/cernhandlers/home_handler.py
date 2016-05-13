# Author: Danilo Piparo 2016
# Copyright CERN

"""CERN Home handler"""

import os

from tornado import web, gen

from jupyterhub.handlers.base import BaseHandler

from .proj_url_checker import check_url

class HomeHandler(BaseHandler):
    """Render the user's home page."""

    @web.authenticated
    def get(self):
        the_user = self.get_current_user()
        the_projurl = self.get_argument('projurl','')

        if the_projurl:
            check_url(the_projurl)
            self.redirect(os.path.join('user', the_user.name, 'tree', the_home_url))

        html = self.render_template('home.html',
            user = the_user
        )

        self.finish(html)
