# Author: Danilo Piparo, Enric Tejedor 2016
# Copyright CERN

"""CERN Spawn handler"""

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
        return self.render_template('spawn.html',
            user=user,
            spawner_options_form=user.spawner.options_form,
            error_message=message,
        )

    def url_add_args(self,url):
       the_projurl = self.get_argument('projurl','')
       if the_projurl:
           check_url(the_projurl)
           url = url_concat(url, {'projurl': projurl})
       return url

    @web.authenticated
    def get(self):
        """GET renders form for spawning with user-specified options"""
        user = self.get_current_user()
        if user.running:
            url = self.url_add_args(user.url)
            self.log.debug("User is running: %s", url)
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
            url = self.url_add_args(user.url)
            self.log.warning("User is already running: %s", url)
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
        url = self.url_add_args(user.url)
        self.redirect(url)
