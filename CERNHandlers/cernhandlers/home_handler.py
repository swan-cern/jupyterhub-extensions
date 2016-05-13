# Author: Danilo Piparo 2016
# Copyright CERN

"""CERN Home handler"""

import os
import subprocess

from tornado import web, gen

from jupyterhub.handlers.base import BaseHandler

from .proj_url_checker import check_url

class HomeHandler(BaseHandler):
    """Render the user's home page."""

    def handle_redirection(self):
        ''' Return projurl and redirection url as a pair'''
        the_projurl = self.get_argument('projurl','')
        if '' == the_projurl: return ('','')

        check_url(the_projurl)

        the_user = self.get_current_user()
        if not the_user.running: return ('','')

        the_user_name = the_user.name
        self.log.info('User %s is running. Fetching project %s.' %(the_user_name,the_projurl))
        command = 'sudo /srv/jupyterhub/fetcher/fetcher.py %s %s %s' %(the_projurl,the_user_name,'SWAN_projects')
        self.log.info('Calling command: %s' %command)
        subprocess.call(command.split())
        proj_name = os.path.basename(the_projurl)
        the_home_url = ''
        if proj_name.endswith('.ipynb'):
            the_home_url = os.path.join('SWAN_projects',proj_name)
        return (the_projurl, the_home_url)

    @web.authenticated
    def get(self):
        the_user = self.get_current_user()
        the_projurl, the_home_url = self.handle_redirection()

        html = self.render_template('home.html',
            user = the_user,
            projurl = the_projurl,
            home_url = the_home_url
        )

        self.finish(html)
