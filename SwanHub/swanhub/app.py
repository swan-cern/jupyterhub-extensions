
import jupyterhub.handlers.pages as pages
import jupyterhub.handlers.base as base
import jupyterhub.apihandlers.users as users
from jupyterhub.utils import url_path_join
from jupyterhub import app
from .spawn_handler import SpawnHandler
from .error_handler import ProxyErrorHandler
from .userapi_handler import SelfAPIHandler
from . import get_templates
from traitlets import default
import sys
import os

handlers_map = {
    pages.SpawnHandler: SpawnHandler,
    pages.ProxyErrorHandler: ProxyErrorHandler,
    users.SelfAPIHandler: SelfAPIHandler
}


class SWAN(app.JupyterHub):
    name = 'swan'

    def init_tornado_settings(self):
        # Add our templates to the end of the list to be used as fallback
        # The upstream templates will be added to the end in the parent init_tornado_settings as well
        swan_templates = get_templates()
        if swan_templates not in self.template_paths:
            self.template_paths.append(swan_templates)
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