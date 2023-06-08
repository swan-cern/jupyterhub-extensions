# Author: Danilo Piparo, Diogo Castro 2015
# Copyright CERN

import jupyterhub.handlers.pages as pages
import jupyterhub.apihandlers.users as users
from jupyterhub import app
from .spawn_handler import SpawnHandler
from .error_handler import ProxyErrorHandler
from .userapi_handler import SelfAPIHandler
from . import get_templates
from traitlets import default
import sys
import os
import datetime

handlers_map = {
    pages.SpawnHandler: SpawnHandler,
    pages.ProxyErrorHandler: ProxyErrorHandler,
    users.SelfAPIHandler: SelfAPIHandler
}


class SWAN(app.JupyterHub):
    name = 'swan'

    @default('template_paths')
    def _template_paths_default(self):
        return [get_templates(), os.path.join(self.data_files_path, 'templates')]

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

        # Add our templates to the end of the list to be used as fallback
        # The upstream templates will be added to the end in the parent init_tornado_settings as well
        for template_path in self._template_paths_default():
            if template_path not in self.template_paths:
                self.template_paths.append(template_path)
        super().init_tornado_settings()

    def init_handlers(self):
        super().init_handlers()
        for i, cur_handler in enumerate(self.handlers):
            new_handler = handlers_map.get(cur_handler[1])
            if new_handler:
                cur_handler = list(cur_handler)
                cur_handler[1] = new_handler
                self.handlers[i] = tuple(cur_handler)

main = SWAN.launch_instance