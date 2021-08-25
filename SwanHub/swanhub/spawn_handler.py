# Author: Danilo Piparo, Enric Tejedor, Diogo Castro 2016
# Copyright CERN

"""CERN Spawn handler"""

import time
import os
import io
import requests
import subprocess
from jupyterhub.handlers.base import BaseHandler
from jupyterhub.handlers.pages import SpawnHandler as JHSpawnHandler
from jupyterhub.utils import url_path_join, maybe_future
from tornado import web
from tornado.httputil import url_concat
from urllib.parse import parse_qs, unquote, urlparse
from .handlers_configs import SpawnHandlersConfigs
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

        if not user.admin and os.path.isfile(configs.maintenance_file):
            self.finish(self.render_template('maintenance.html'))
            return

        if 'failed' in self.request.query_arguments:
            form = await self._render_form_wrapper(user, message=configs.spawn_error_message)
            self.finish(form)
            return

        if not self.allow_named_servers and for_user is None:
            if 'changeconfig' in self.request.query_arguments:
                self._swanrc_delete(user.name)
            else:
                form_options = self._swanrc_read(user.name)
                if form_options:
                    self.log.info('User has default session configuration: loading saved options')
                    await self._spawn(user, '', form_options, configs)
                    return

        try:
            await super().get(for_user, server_name)
        except web.HTTPError as e:
            form = await self._render_form_wrapper(user, message=e.message)
            self.finish(form)
            return

    @web.authenticated
    async def post(self, for_user=None, server_name=''):
        """POST spawns with user-specified options"""
        self.log.info("Handling spawner POST request")

        configs = SpawnHandlersConfigs.instance()
        user = current_user = self.current_user

        if for_user is not None and for_user != user.name:
            if not user.admin:
                raise web.HTTPError(
                    403, "Only admins can spawn on behalf of other users"
                )
            user = self.find_user(for_user)
            if user is None:
                raise web.HTTPError(404, "No such user: %s" % for_user)

        if not current_user.admin and os.path.isfile(configs.maintenance_file):
            self.finish(self.render_template('maintenance.html'))
            return

        form_options = {}
        for key, byte_list in self.request.body_arguments.items():
            if key == 'keep-config':
                continue
            form_options[key] = [bs.decode('utf8') for bs in byte_list]
        for key, byte_list in self.request.files.items():
            form_options["%s_file" % key] = byte_list

        if 'keep-config' in self.request.body_arguments:
            self._swanrc_write(user.name, form_options)

        await self._spawn(user, server_name, form_options, configs)

    async def _spawn(self, user, server_name, form_options, configs):
        # log spawn start time
        current_user = self.current_user
        spawner = user.spawners[server_name]

        if spawner.ready:
            raise web.HTTPError(400, "%s is already running" %
                                (spawner._log_name))
        elif spawner.pending:
            raise web.HTTPError(
                400, "%s is pending %s" % (spawner._log_name, spawner.pending)
            )

        start_time_spawn = time.time()

        try:
            options = await maybe_future(spawner.options_from_form(form_options))
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
        next_url = self.get_next_url(
            user,
            default=url_path_join(
                self.hub.base_url, "spawn-pending", user.escaped_name, server_name
            ),
        )
        self.redirect(next_url)

    async def _render_form_wrapper(self, for_user, message=''):
        spawner_options_form = await for_user.spawner.get_options_form()
        form = self._render_form(for_user, spawner_options_form, message)
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
                                    url=self.request.uri,
                                    spawner=for_user.spawner,
                                    save_config=save_config
                                    )

    def _swanrc_read(self, user):
        """ Read the user's swanrc file stored in CERNBox.
            This file contains the user's session configuration in order to automatically start the session when accessing SWAN.
            Swanrc bash scripts runs as the user in order to read his files.
        """
        options = {}
        configs = SpawnHandlersConfigs.instance()
        if not configs.local_home:
            subprocess.call(
                ['sudo', '/srv/jupyterhub/culler/check_ticket.sh', user])
            rc = subprocess.Popen(
                ['sudo', configs.swanrc_path, 'read', user], stdout=subprocess.PIPE)
            for line in io.TextIOWrapper(rc.stdout, encoding="utf-8"):
                if line == 0:
                    break
                line_split = line.split('=')
                if len(line_split) == 2:
                    options[line_split[0]] = [line_split[1].rstrip('\n')]

        return options

    def _swanrc_write(self, user, options):
        """Write the configurations selected in a .swanrc file inside user's CERNBox"""
        new_list = []
        for key in options:
            new_list.append('%s=%s' % (key, options[key][0]))

        configs = SpawnHandlersConfigs.instance()
        if not configs.local_home:
            subprocess.call(['sudo', configs.swanrc_path, 'write',
                             user, " ".join(new_list).replace('$', '\$')])

    def _swanrc_delete(self, user):
        """Remove the configuration file in order to start a new configuration"""
        configs = SpawnHandlersConfigs.instance()
        if not configs.local_home:
            subprocess.call(['sudo', configs.swanrc_path, 'remove', user])

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
            [options[configs.lcg_rel_field], options[configs.spark_cluster_field]])
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
