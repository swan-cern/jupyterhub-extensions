# Author: Danilo Piparo, Enric Tejedor, Diogo Castro 2016
# Copyright CERN

"""CERN Spawn handler"""

import time
import os
from jupyterhub.handlers.pages import SpawnHandler as JHSpawnHandler
from jupyterhub.utils import url_path_join, maybe_future
from jupyterhub.scopes import needs_scope
from tornado import web
from .handlers_configs import SpawnHandlersConfigs
from tornado.httputil import url_concat
import datetime
import calendar
import pickle
import struct
from socket import (
    socket,
    AF_INET,
    SOCK_STREAM,
    gethostname,
)


class SpawnHandler(JHSpawnHandler):
    """Handle spawning of single-user servers via form.

    GET renders the form, POST handles form submission.

    Only enabled when Spawner.options_form is defined.
    """

    @web.authenticated
    async def get(self, for_user=None, server_name=''):
        """
        GET renders user-specified options spawn-form or spawns a session if 'always start with this configuration'
        was selected
        """

        self.log.info("Handling spawner GET request")

        configs = SpawnHandlersConfigs.instance()
        user = self.current_user

        # FIXME with RBAC the admin property looks like it has changed,
        # but we're going to drop this code soon either way...
        if not user.admin and os.path.isfile(configs.maintenance_file):
            self.finish(await self.render_template('maintenance.html'))
            return

        if 'failed' in self.request.query_arguments:
            form = await self._render_form_wrapper(user, message=configs.spawn_error_message)
            self.finish(form)
            return

        # By default, the super().get() starts spawning the session if any
        # query arguments are specified. So, we need to explicitly check for
        # the software_source query argument to re-render the form and fill
        # it with the remaining query arguments.
        if configs.software_source in self.request.query_arguments:
            form = await self._render_form_wrapper(user)
            self.finish(form)
            return

        try:
            await super().get(for_user, server_name)
        except web.HTTPError as e:
            form = await self._render_form_wrapper(user, message=e.message)
            self.finish(form)
            return

    @web.authenticated
    def post(self, user_name=None, server_name=''):
        """POST spawns with user-specified options"""
        self.log.info("Handling spawner POST request")

        configs = SpawnHandlersConfigs.instance()
        current_user = self.current_user

        if not current_user.admin and os.path.isfile(configs.maintenance_file):
            self.finish(self.render_template('maintenance.html'))
            return
        
        if user_name is None:
            user_name = self.current_user.name
        if server_name is None:
            server_name = ""
        return self._post(user_name=user_name, server_name=server_name)

    @needs_scope("servers")
    async def _post(self, user_name, server_name):
        configs = SpawnHandlersConfigs.instance()
        for_user = user_name
        user = current_user = self.current_user

        if for_user != user.name:
            user = self.find_user(for_user)
            if user is None:
                raise web.HTTPError(404, "No such user: %s" % for_user)
            
        spawner = user.get_spawner(server_name, replace_failed=True)

        if spawner.ready:
            raise web.HTTPError(400, "%s is already running" % (spawner._log_name))
        elif spawner.pending:
            raise web.HTTPError(
                400, f"{spawner._log_name} is pending {spawner.pending}"
            )

        form_options = {}
        for key, byte_list in self.request.body_arguments.items():
            form_options[key] = [bs.decode('utf8') for bs in byte_list]
        for key, byte_list in self.request.files.items():
            form_options["%s_file" % key] = byte_list

        start_time_spawn = time.time()

        options = {}
        try:
            options = await maybe_future(spawner.run_options_from_form(form_options))
            await self.spawn_single_user(user, server_name=server_name, options=options)

            # if spawn future is already done it is success,
            # otherwise add done callback to spawn future
            if spawner._spawn_future and not spawner._spawn_future.done():
                def _finish_spawn(f):
                    """
                    Future done callback called at the termination of user.spawner._spawn_future,
                    used to report spawn metrics
                    """
                    if f.exception() is None:
                        # log successful spawn
                        self._log_spawn_metrics(
                            user, options, time.time() - start_time_spawn)
                    else:
                        # log failed spawn
                        self._log_spawn_metrics(
                            user, options, time.time() - start_time_spawn, f.exception())
                        self.log.error(
                            "Failed to spawn single-user server", exc_info=True)

                user.spawner._spawn_future.add_done_callback(_finish_spawn)
            else:
                self._log_spawn_metrics(
                    user, options, time.time() - start_time_spawn)

        except Exception as e:
            self._log_spawn_metrics(
                user, options, time.time() - start_time_spawn, e)

            if type(e) in (web.HTTPError, TimeoutError):
                error_message = configs.spawn_error_message
                self.log.warning(
                    "Failed to spawn single-user server with known error", exc_info=True)
            else:
                error_message = str(e)
                self.log.error(
                    "Failed to spawn single-user server with form", exc_info=True)

            form = await self._render_form_wrapper(user, message=error_message)
            self.finish(form)
            return

        if current_user is user:
            self.set_login_cookie(user)


        if options.get(configs.software_source) == configs.customenv_special_type:
            # Add the query parameters to the URL
            query_params = {
                "repo": options.get(configs.repository),
                configs.builder: options.get(configs.builder),
                configs.file: options.get(configs.file, ''),
            }
            # If the builder has a version, pass it as an argument of the query
            if options.get(configs.builder_version):
                query_params[configs.builder_version] = options[configs.builder_version]
            if options.get(configs.spark_cluster_field, "none") != "none":
                query_params["nxcals"] = True

            # Execution SwanCustomEnvs extension with the corresponding query arguments
            next_url = url_concat(url_path_join("user", user.escaped_name, "customenvs", server_name), query_params)
        else: # LCG release
            next_url = url_path_join(self.hub.base_url, "spawn-pending", user.escaped_name, server_name)
            if options.get(configs.file) and options[configs.use_jupyterlab_field] == 'checked':
                next_url = url_path_join("user", user.escaped_name, "lab", "tree", *options[configs.file].split('/'))

        self.redirect(next_url)

    async def _render_form_wrapper(self, for_user, message=''):
        spawner_options_form = await for_user.spawner.get_options_form()
        form = await self._render_form(for_user, spawner_options_form, message)
        return form

    async def _render_form(self, for_user, spawner_options_form, message=''):
        configs = SpawnHandlersConfigs.instance()
        auth_state = await for_user.get_auth_state()

        save_config = not configs.local_home and not self.allow_named_servers

        return await self.render_template('spawn.html',
                                    for_user=for_user,
                                    auth_state=auth_state,
                                    spawner_options_form=spawner_options_form,
                                    error_message=message,
                                    url=url_concat(
                                        self.request.uri, {"_xsrf": self.xsrf_token.decode('ascii')}
                                    ),
                                    spawner=for_user.spawner,
                                    save_config=save_config
                                    )


    def _log_spawn_metrics(self, user, options, spawn_duration_sec, spawn_exception=None):
        """
        Log and send user chosen options to the metrics server.
        This will allow us to see what users are choosing from within Grafana.
        """

        date = calendar.timegm(datetime.datetime.utcnow().timetuple())
        host = gethostname().split('.')[0]
        configs = SpawnHandlersConfigs.instance()

        # Add options to the log and send as metrics
        metrics = []
        for (key, value) in options.items():
            if key == configs.user_script_env_field:
                path = ".".join(
                    [configs.graphite_metric_path, host, 'spawn_form', key])
                metrics.append((path, (date, 1 if value else 0)))
            else:
                value_cleaned = str(value).replace('/', '_')

                self._log_metric(user.name, host, ".".join(
                    ['spawn_form', key]), value_cleaned)

                metric = ".".join(
                    [configs.graphite_metric_path, host, 'spawn_form', key, value_cleaned])
                metrics.append((metric, (date, 1)))

        spawn_context_key = ".".join(
            [options.get(configs.lcg_rel_field, "CustomEnv"), options.get(configs.spark_cluster_field, "none")])
        if not spawn_exception:
            # Add spawn success (no exception) and duration to the log and send as metrics
            spawn_exc_class = "None"
            self._log_metric(user.name, host, ".".join(
                ["spawn", spawn_context_key, "exception_class"]), spawn_exc_class)
            self._log_metric(user.name, host, ".".join(
                ["spawn", spawn_context_key, "duration_sec"]), spawn_duration_sec)
            metrics.append((".".join(
                [configs.graphite_metric_path, host, "spawn_exception", spawn_exc_class]), (date, 1)))
            metrics.append((".".join([configs.graphite_metric_path, host, "spawn_duration_sec", str(
                spawn_duration_sec)]), (date, 1)))
        else:
            # Log spawn exception (send exception as metric)
            spawn_exc_class = spawn_exception.__class__.__name__
            self._log_metric(user.name, host, ".".join(
                ["spawn", spawn_context_key, "exception_class"]), spawn_exc_class)
            self._log_metric(user.name, host, ".".join(
                ["spawn", spawn_context_key, "exception_message"]), str(spawn_exception))
            metrics.append((".".join(
                [configs.graphite_metric_path, host, "spawn_exception", spawn_exc_class]), (date, 1)))

        if configs.metrics_on:
            self._send_graphite_metrics(metrics)

    def _log_metric(self, user, host, metric, value):
        self.log.info("user: %s, host: %s, metric: %s, value: %s" %
                      (user, host, metric, value))

    def _send_graphite_metrics(self, metrics):
        """
        Send metrics to the metrics server for analysis in Grafana.
        """

        self.log.debug("sending metrics to graphite: %s", metrics)

        try:
            configs = SpawnHandlersConfigs.instance()
            # Serialize the message and send everything in on single package
            payload = pickle.dumps(metrics, protocol=2)
            header = struct.pack("!L", len(payload))
            message = header + payload

            # Send the message
            conn = socket(AF_INET, SOCK_STREAM)
            conn.settimeout(2)
            conn.connect((configs.graphite_server,
                          configs.graphite_server_port_batch))
            conn.send(message)
            conn.close()
        except Exception as ex:
            self.log.error("Failed to send metrics: %s", ex, exc_info=True)
