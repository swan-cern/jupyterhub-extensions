# Author: Danilo Piparo, Enric Tejedor 2016
# Copyright CERN

"""CERN Spawn handler"""

import time
import os
import io
import requests
import subprocess
from jupyterhub.handlers.base import BaseHandler
from jupyterhub.utils import url_path_join
from tornado import web
from tornado.httputil import url_concat
from urllib.parse import parse_qs, unquote, urlparse
from .handlers_configs import SpawnHandlersConfigs
import datetime, calendar
import pickle, struct
from socket import (
    socket,
    AF_INET,
    SOCK_STREAM,
    gethostname,
)

class SpawnHandler(BaseHandler):
    """Handle spawning of single-user servers via form.

    GET renders the form, POST handles form submission.

    Only enabled when Spawner.options_form is defined.
    """

    async def _render_form(self, message=''):
        configs = SpawnHandlersConfigs.instance()
        user = self.get_current_user()
        # We inject an extra field if there is a project set
        the_projurl = self.get_projurl()
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
            the_projurl = self.get_projurl()
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

    def get_projurl(self):
        projurl = self.get_argument('projurl','')
        if not projurl:
            next_url = self.get_argument('next','')
            if next_url:
                unquoted_next = unquote(unquote(next_url))
                parsed_qs = parse_qs(urlparse(unquoted_next).query)
                if 'projurl' in parsed_qs:
                    projurl = parsed_qs['projurl'][0]
        return projurl


    @web.authenticated
    async def get(self):
        """
        GET renders user-specified options spawn-form or spawns a session if 'always start with this configuration'
        was selected
        """

        self.log.info("Handling spawner GET request")

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
                if await self._start_spawn(user, form_options, configs):
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
        self.log.info("Handling spawner POST request")

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
        # log spawn start time
        start_time_spawn = time.time()

        # get options and log them before spawn
        options = user.spawner.options_from_form(form_options)

        try:
            # spawn user and await single user server
            await self.spawn_single_user(user, options=options)

            self.set_login_cookie(user)

            # if spawn future is already done it is success,
            # otherwise add done callback to spawn future
            if user.spawner._spawn_future and not user.spawner._spawn_future.done():
                def _finish_spawn(f):
                    """
                    Future done callback called at the termination of user.spawner._spawn_future,
                    used to report spawn metrics
                    """
                    if f.exception() is None:
                        # log successful spawn
                        self._log_spawn_metrics(user, options, time.time() - start_time_spawn)
                    else:
                        # log failed spawn
                        self._log_spawn_metrics(user, options, time.time() - start_time_spawn, f.exception())
                        self.log.error("Failed to spawn single-user server with form", exc_info=True)

                user.spawner._spawn_future.add_done_callback(_finish_spawn)
            else:
                self._log_spawn_metrics(user, options, time.time() - start_time_spawn)

            return 0
        except (web.HTTPError, TimeoutError) as e: # Handle failed/timeout startups with our message
            form = await self._render_form(message=configs.spawn_error_message)
            self._log_spawn_metrics(user, options, time.time() - start_time_spawn, e)
        except Exception as e: # Show other errors to the user
            form = await self._render_form(message=str(e))
            self._log_spawn_metrics(user, options, time.time() - start_time_spawn, e)

        self.log.error("Failed to spawn single-user server with form", exc_info=True)

        self.finish(form)

        return 1

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
                path = ".".join([configs.graphite_metric_path, host, 'spawn_form', key])
                metrics.append((path, (date, 1 if value else 0)))
            else:
                value_cleaned = str(value).replace('/', '_')

                self._log_metric(user.name, host, ".".join(['spawn_form', key]), value_cleaned)

                metric = ".".join([configs.graphite_metric_path, host, 'spawn_form', key, value_cleaned])
                metrics.append((metric, (date, 1)))

        if not spawn_exception:
            # Add spawn success (no exception) and duration to the log and send as metrics
            self._log_metric(user.name, host, "spawn.exception_class", "None")
            self._log_metric(user.name, host, "spawn.duration_sec", spawn_duration_sec)
            metrics.append((".".join([configs.graphite_metric_path, host, "spawn_exception", "None"]), (date, 1)))
            metrics.append((".".join([configs.graphite_metric_path, host, "spawn_duration_sec", str(spawn_duration_sec)]), (date, 1)))
        else:
            # Log spawn exception (send exception as metric)
            spawn_exc_class = spawn_exception.__class__.__name__
            self._log_metric(user.name, host, "spawn.exception_class", spawn_exc_class)
            self._log_metric(user.name, host, "spawn.exception_message", str(spawn_exception))
            metrics.append((".".join([configs.graphite_metric_path, host, "spawn_exception", spawn_exc_class]), (date, 1)))

        if configs.metrics_on:
            self._send_graphite_metrics(metrics)

    def _log_metric(self, user, host, metric, value):
        self.log.info("user: %s, host: %s, metric: %s, value: %s" % (user, host, metric, value))

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
            conn.connect((configs.graphite_server, configs.graphite_server_port_batch))
            conn.send(message)
            conn.close()
        except Exception as ex:
            self.log.error("Failed to send metrics: %s", ex, exc_info=True)


