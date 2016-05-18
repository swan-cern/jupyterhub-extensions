# Author: Danilo Piparo, Enric Tejedor 2016
# Copyright CERN

"""CERN Spawn handler"""

import os
import subprocess

from tornado import web, gen
from tornado.httputil import url_concat

from jupyterhub.utils import url_path_join
from jupyterhub.handlers.base import BaseHandler

from .proj_url_checker import check_url

class SpawnHandler(BaseHandler):
    """Handle spawning of single-user servers via form.

    GET renders the form, POST handles form submission.

    Only enabled when Spawner.options_form is defined.
    """

    def _render_form(self, message=''):
        user = self.get_current_user()
        # We inject an extra field if there is a project set
        the_projurl = self.get_argument('projurl','')
        the_form = user.spawner.options_form
        if the_projurl:
            the_form +='<input type="hidden" name="projurl" value="%s">' %the_projurl
        return self.render_template('spawn.html',
            user=user,
            spawner_options_form=the_form,
            error_message=message,
        )

    def handle_redirection(self, the_projurl = ''):
        ''' Return redirection url'''
        if not the_projurl:
            the_projurl = self.get_argument('projurl','')
        if not the_projurl: return ''

        check_url(the_projurl)

        the_user = self.get_current_user()
#        if not the_user.running: return ''

        the_user_name = the_user.name
        self.log.info('User %s is running. Fetching project %s.' %(the_user_name,the_projurl))
        command = 'sudo /srv/jupyterhub/fetcher/fetcher.py %s %s %s' %(the_projurl,the_user_name,'SWAN_projects')
        self.log.info('Calling command: %s' %command)
        subprocess.call(command.split())
        proj_name = os.path.basename(the_projurl)
        the_home_url = ''
        if proj_name.endswith('.ipynb'): # git repo to be added
            the_home_url = os.path.join('SWAN_projects',proj_name)
        return the_home_url

    @web.authenticated
    def get(self):
        """GET renders form for spawning with user-specified options"""
        user = self.get_current_user()
        if user.running:
            url = user.url
            self.log.warning("User is running: %s", url)
            redirect_url = self.handle_redirection()
            if redirect_url:
                url = os.path.join(url, 'tree', redirect_url)
            self.redirect(url)
            return
        if user.spawner.options_form:
            self.finish(self._render_form())
        else:
            # not running, no form. Trigger spawn.
            url = url_path_join(self.base_url, 'user', user.name)
            self.redirect(url)

    @web.authenticated
    @gen.coroutine
    def post(self):
        """POST spawns with user-specified options"""
        user = self.get_current_user()
        if user.running:
            url = user.url
            self.log.debug("User is already running: %s", url)
            self.redirect(url)
            return
        form_options = {}
        for key, byte_list in self.request.body_arguments.items():
            form_options[key] = [ bs.decode('utf8') for bs in byte_list ]
        for key, byte_list in self.request.files.items():
            form_options["%s_file"%key] = byte_list
        try:
            options = user.spawner.options_from_form(form_options)
            yield self.spawn_single_user(user, options=options)
        except Exception as e:
            self.log.error("Failed to spawn single-user server with form", exc_info=True)
            self.finish(self._render_form(str(e)))
            return
        self.set_login_cookie(user)
        url = user.url
        projurl_key = 'projurl'
        if projurl_key in self.request.body_arguments:
            the_projurl = self.request.body_arguments['projurl'][0].decode('utf8')
            redirect_url = self.handle_redirection(the_projurl)
            url = os.path.join(url, 'tree', redirect_url)
        self.redirect(url)
