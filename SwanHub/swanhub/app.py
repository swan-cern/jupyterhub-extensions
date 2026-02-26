# Author: Danilo Piparo, Diogo Castro 2015
# Copyright CERN

import datetime
import os

from jupyterhub import app
from jupyterhub.apihandlers import users
from jupyterhub.handlers import pages
from traitlets import default

from . import get_templates
from .error_handler import ProxyErrorHandler
from .spawn_handler import SpawnHandler
from .userapi_handler import SelfAPIHandler

handlers_map = {
    pages.SpawnHandler: SpawnHandler,
    pages.ProxyErrorHandler: ProxyErrorHandler,
    users.SelfAPIHandler: SelfAPIHandler
}


class SWAN(app.JupyterHub):
    name = 'swan'

    @default('logo_file')
    def _logo_file_default(self):
        return os.path.join(
            self.data_files_path, 'static', 'swan', 'logos', 'logo_swan_cloudhisto.png'
        )

    @default('load_roles')
    def _load_roles_default(self):
        # Ensure that users can see their own auth_state
        # This allows retrieving the up to date tokens and put them inside
        # the user container
        # Replace this config with care
        return [
            {
                "name": "user",
                "scopes": ["self", "admin:auth_state!user"]
            },
            {
                'name': 'server',
                'scopes': ["access:servers!user", "read:users:activity!user", "users:activity!user", "admin:auth_state!user"]
            }
        ]

    def init_tornado_settings(self):
        self.template_vars['current_year'] = datetime.datetime.now().year # For copyright message
        if datetime.date.today().month == 12:
            # It's Christmas time!
            self.template_vars['swan_logo_filename'] = 'swan_letters_christmas.png'
        else:
            self.template_vars['swan_logo_filename'] = 'logo_swan_letters.png'

        # Register SwanHub templates with the correct priority:
        # Hub config (c.JupyterHub.template_paths) >> SwanHub templates >> JupyterHub default templates
        swan_path = get_templates()
        if swan_path not in self.template_paths:
            default_path = self._template_paths_default()[0]
            # Remove the default JupyterHub templates path (will be present if c.JupyterHub.template_paths is not set)
            # This is to ensure correct ordering of template paths. The default templates will be re-added again
            # by super().init_tornado_settings() at the end.
            if default_path in self.template_paths:
                self.template_paths.remove(default_path)
            self.template_paths.append(swan_path)

        super().init_tornado_settings()
        # At this point, self.template_paths should be either:
        # - [swan_path, default_path] (c.JupyterHub.template_paths not set)
        # - [c.JupyterHub.template_paths, swan_path, default_path] (c.JupyterHub.template_paths set)

    def init_handlers(self):
        super().init_handlers()
        for i, cur_handler in enumerate(self.handlers):
            new_handler = handlers_map.get(cur_handler[1])
            if new_handler:
                cur_handler = list(cur_handler)
                cur_handler[1] = new_handler
                self.handlers[i] = tuple(cur_handler)

main = SWAN.launch_instance
