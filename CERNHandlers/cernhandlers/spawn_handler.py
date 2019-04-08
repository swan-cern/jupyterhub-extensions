# Author: Danilo Piparo, Enric Tejedor 2016
# Copyright CERN

"""CERN Spawn handler"""

import os
import io
import requests
import subprocess
from jupyterhub.handlers.base import BaseHandler
from jupyterhub.utils import url_path_join
from tornado import web, gen
from tornado.httputil import url_concat

from .handlers_configs import SpawnHandlersConfigs

class SpawnHandler(BaseHandler):
    """Handle spawning of single-user servers via form.

    GET renders the form, POST handles form submission.

    Only enabled when Spawner.options_form is defined.
    """

    async def _render_form(self, message=''):
        configs = SpawnHandlersConfigs.instance()
        user = self.get_current_user()
        # We inject an extra field if there is a project set
        the_projurl = self.get_argument('projurl','')
        the_form = open(user.spawner.options_form).read()
        if the_projurl:
            the_form +='<input type="hidden" name="projurl" value="%s">' % the_projurl
        return self.render_template('spawn.html',
            user=user,
            spawner_options_form=the_form,
            error_message=message,
            local_home=configs.local_home,
            url=self.request.uri
        )

    def handle_redirection(self, the_projurl = ''):
        ''' Return redirection url'''
        if not the_projurl:
            the_projurl = self.get_argument('projurl','')
        if not the_projurl: return ''

        return 'download?projurl=' + the_projurl

    def read_swanrc_options(self, user):
        """ Read the user's swanrc file stored in CERNBox.
            This file contains the user's session configuration in order to automatically start the session when accessing SWAN.
            Swanrc bash scripts runs as the user in order to read his files.
        """
        options = {}
        configs = SpawnHandlersConfigs.instance()
        if not configs.local_home:
            subprocess.call(['sudo', '/srv/jupyterhub/culler/check_ticket.sh', user])
            rc = subprocess.Popen(['sudo', configs.swanrc_path, 'read', user], stdout=subprocess.PIPE)
            for line in io.TextIOWrapper(rc.stdout, encoding="utf-8"):
                if line == 0:
                    break
                line_split = line.split('=')
                if len(line_split) == 2:
                    options[line_split[0]] = [line_split[1].rstrip('\n')]

        return options

    def write_swanrc_options(self, user, options):
        """Write the configurations selected in a .swanrc file inside user's CERNBox"""
        new_list = []
        for key in options:
            new_list.append('%s=%s' % (key, options[key][0]))

        configs = SpawnHandlersConfigs.instance()
        if not configs.local_home:
            subprocess.call(['sudo', configs.swanrc_path, 'write', user, " ".join(new_list).replace('$', '\$')])

    def remove_swanrc_options(self, user):
        """Remove the configuration file in order to start a new configuration"""
        configs = SpawnHandlersConfigs.instance()
        if not configs.local_home:
            subprocess.call(['sudo', configs.swanrc_path, 'remove', user])


    @web.authenticated
    async def get(self):
        """GET renders form for spawning with user-specified options"""
        configs = SpawnHandlersConfigs.instance()
        user = self.get_current_user()

        if user.running:
            url = user.url
            self.log.warning("User is running: %s", url)
            redirect_url = self.handle_redirection()
            if redirect_url:
                url = os.path.join(url, redirect_url)
            else:
                url = os.path.join(url, configs.start_page)
            self.redirect(url)
            return

        if os.path.isfile(configs.maintenance_file):
            self.finish(self.render_template('maintenance.html'))
            return

        if 'failed' in self.request.query_arguments:
            form = await self._render_form(message=configs.spawn_error_message)
            self.finish(form)
            return

        if 'changeconfig' in self.request.query_arguments:
            self.remove_swanrc_options(user.name)
        else:
            form_options = self.read_swanrc_options(user.name)
            if form_options:
                self.log.info('User has default session configuration: loading saved options')
                if await self._start_spawn(user, form_options):
                    return
                url = user.url
                projurl_key = 'projurl'
                if projurl_key in self.request.body_arguments:
                    the_projurl = self.request.body_arguments['projurl'][0].decode('utf8')
                    redirect_url = self.handle_redirection(the_projurl)
                    url = os.path.join(url, redirect_url)
                self.redirect(os.path.join(url))
                return

        if user.spawner.options_form:
            form = await self._render_form()
            self.finish(form)
        else:
            # not running, no form. Trigger spawn.
            url = url_path_join(self.base_url, 'user', user.name)
            self.redirect(url)

    @web.authenticated
    async def post(self):
        """POST spawns with user-specified options"""
        configs = SpawnHandlersConfigs.instance()
        user = self.get_current_user()
        if user.running:
            url = os.path.join(user.url, configs.start_page)
            self.log.debug("User is already running: %s", url)
            self.redirect(url)
            return

        if user.spawner.pending:
            raise web.HTTPError(
                400, "%s is pending %s" % (user.spawner._log_name, user.spawner.pending)
            )

        if os.path.isfile(configs.maintenance_file):
            self.finish(self.render_template('maintenance.html'))
            return

        form_options = {}
        for key, byte_list in self.request.body_arguments.items():
            if key == 'keep-config':
                continue
            form_options[key] = [ bs.decode('utf8') for bs in byte_list ]
        for key, byte_list in self.request.files.items():
            form_options["%s_file"%key] = byte_list

        if 'keep-config' in self.request.body_arguments:
            self.write_swanrc_options(user.name, form_options)

        if await self._start_spawn(user, form_options, configs):
            return

        url = user.url
        projurl_key = 'projurl'
        if projurl_key in self.request.body_arguments:
            the_projurl = self.request.body_arguments['projurl'][0].decode('utf8')
            redirect_url = self.handle_redirection(the_projurl)
            url = os.path.join(url, redirect_url)
        else:
            url = os.path.join(url, configs.start_page)
        self.redirect(url)

    # Spawn the session and return the status (0 ok, 1 error)
    async def _start_spawn(self, user, form_options, configs):
        try:
            options = user.spawner.options_from_form(form_options)
            await self.spawn_single_user(user, options=options)
            self.set_login_cookie(user)
            return 0
        except web.HTTPError: #Handle failed startups with our message
            form = await self._render_form(message=configs.spawn_error_message)
        except Exception as e: #Show other errors to the user
            form = await self._render_form(message=str(e))
        self.log.error("Failed to spawn single-user server with form", exc_info=True)
        self.finish(form)
        return 1