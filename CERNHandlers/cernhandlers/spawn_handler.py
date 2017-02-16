# Author: Danilo Piparo, Enric Tejedor 2016
# Copyright CERN

"""CERN Spawn handler"""

import os
import requests
import subprocess

from tornado import web, gen
from tornado.httputil import url_concat

from jupyterhub.utils import url_path_join
from jupyterhub.handlers.base import BaseHandler

from .proj_url_checker import check_url, is_good_proj_name, is_file_on_eos, is_cernbox_shared_link, get_name_from_shared_from_link

class SpawnHandler(BaseHandler):
    """Handle spawning of single-user servers via form.

    GET renders the form, POST handles form submission.

    Only enabled when Spawner.options_form is defined.
    """

    def _render_form(self, message=''):
        user = self.get_current_user()
        # We inject an extra field if there is a project set
        the_projurl = self.get_argument('projurl','')
        the_form = open(user.spawner.options_form).read()
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

        the_user_name = the_user.name
        self.log.info('User %s is running. Fetching project %s.' %(the_user_name,the_projurl))
        isFileOnEos = is_file_on_eos(the_projurl)
        isFileOnCERNBoxShare = is_cernbox_shared_link(the_projurl)
        if not isFileOnEos:
            command = ['sudo', '/srv/jupyterhub/fetcher/fetcher.py', the_projurl, the_user_name, 'SWAN_projects']
            self.log.info('Calling command: %s' %command)
            subprocess.call(command)
        proj_name = os.path.basename(the_projurl)
        if isFileOnCERNBoxShare:
            r = requests.get(the_projurl, verify=False)
            proj_name = get_name_from_shared_from_link(r)
        the_home_url = ''
        if is_good_proj_name(proj_name):
            if proj_name.endswith('.ipynb'):
                if is_file_on_eos(the_projurl):
                    # We need of file://eos/user/j/joe/A/B/C/d.ipynb only A/B/C/d.ipynb
                    the_home_url = '/'.join(the_projurl.split('/')[6:])
                else:
                    the_home_url = os.path.join('SWAN_projects', proj_name)
            else:
                # Default case
                path_to_proj = os.path.splitext(proj_name)[0]

                # Check for an index.ipynb in the github and gitlab case
                the_projurl_noext = os.path.splitext(the_projurl)[0]
                index_name = 'index.ipynb'
                index_nb = ''
                if the_projurl.startswith('https://github.com'):
                    raw_projurl_noext = the_projurl_noext.replace('https://github.com', 'https://raw.githubusercontent.com')
                    index_nb = os.path.join(raw_projurl_noext, 'master', index_name)
                if the_projurl.startswith('https://gitlab.cern.ch'):
                    index_nb = os.path.join(the_projurl_noext, 'raw', 'master', index_name)

                if '' != index_nb and requests.get(index_nb).status_code == 200:
                    the_home_url = os.path.join('SWAN_projects', path_to_proj, index_name)
                else:
                    the_home_url = os.path.join('SWAN_projects', path_to_proj)
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
