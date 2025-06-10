"""script to monitor and cull idle single-user servers

Adapted to SWAN from https://github.com/jupyterhub/jupyterhub/blob/1.1.0/examples/cull-idle/cull_idle_servers.py

Caveats:

last_activity is not updated with high frequency,
so cull timeout should be greater than the sum of:

- single-user websocket ping interval (default: 30s)
- JupyterHub.last_activity_interval (default: 5 minutes)

You can run this as a service managed by JupyterHub with this in your config::


    c.JupyterHub.services = [
        {
            'name': 'cull-idle',
            'admin': True,
            'command': [sys.executable, 'cull_idle_servers.py', '--timeout=3600'],
        }
    ]

Or run it manually by generating an API token and storing it in `JUPYTERHUB_API_TOKEN`:

    export JUPYTERHUB_API_TOKEN=$(jupyterhub token)
    python3 cull_idle_servers.py [--timeout=900] [--url=http://127.0.0.1:8081/hub/api]

This script uses the same ``--timeout`` and ``--max-age`` values for
culling users and users' servers.  If you want a different value for
users and servers, you should add this script to the services list
twice, just with different ``name``s, different values, and one with
the ``--cull-users`` option.
"""
import json
import os
from datetime import datetime
from datetime import timezone
from functools import partial

try:
    from urllib.parse import quote, urlencode
except ImportError:
    from urllib import quote, urlencode

import dateutil.parser

from tornado.gen import coroutine, multi
from tornado.locks import Semaphore
from tornado.log import app_log
from tornado.httpclient import AsyncHTTPClient, HTTPRequest,HTTPClientError
from tornado.ioloop import IOLoop, PeriodicCallback
from tornado.options import define, options, parse_command_line

# Start SWAN code
from subprocess import call

def check_ticket(username):
    app_log.info("Checking ticket for user %s", username)
    call(['sudo', '--preserve-env=SWAN_DEV', "%s/check_ticket.sh" % options.hooks_dir, username])
# End SWAN code

def parse_date(date_string):
    """Parse a timestamp

    If it doesn't have a timezone, assume utc

    Returned datetime object will always be timezone-aware
    """
    dt = dateutil.parser.parse(date_string)
    if not dt.tzinfo:
        # assume naïve timestamps are UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def format_td(td):
    """
    Nicely format a timedelta object

    as HH:MM:SS
    """
    if td is None:
        return "unknown"
    if isinstance(td, str):
        return td
    seconds = int(td.total_seconds())
    h = seconds // 3600
    seconds = seconds % 3600
    m = seconds // 60
    seconds = seconds % 60
    return "{h:02}:{m:02}:{seconds:02}".format(h=h, m=m, seconds=seconds)

@coroutine
def delete_server(user_name, server_name, url, auth_header, fetch):
    if server_name:
        # culling a named server
        delete_url = url + "/users/%s/servers/%s" % (
            quote(user_name),
            quote(server_name),
        )
    else:
        delete_url = url + '/users/%s/server' % quote(user_name)
    
    req = HTTPRequest(url=delete_url, method='DELETE', headers=auth_header)
    resp = yield fetch(req)
    return resp

@coroutine
def delete_user(user_name, url, auth_header, fetch):
    req = HTTPRequest(
        url=url + '/users/%s' % user_name, method='DELETE', headers=auth_header
    )
    resp = yield fetch(req)
    return resp

@coroutine
def cull_idle(
    url, api_token, inactive_limit, cull_users=False, disable_hooks=False, max_age=0, concurrency=10
):
    """Shutdown idle single-user servers

    If cull_users, inactive *users* will be deleted as well.
    """
    auth_header = {'Authorization': 'token %s' % api_token}
    req = HTTPRequest(url=url + '/users', headers=auth_header)
    now = datetime.now(timezone.utc)
    client = AsyncHTTPClient()

    if concurrency:
        semaphore = Semaphore(concurrency)

        @coroutine
        def fetch(req):
            """client.fetch wrapped in a semaphore to limit concurrency"""
            yield semaphore.acquire()
            try:
                return (yield client.fetch(req))
            finally:
                yield semaphore.release()

    else:
        fetch = client.fetch

    resp = yield fetch(req)
    users = json.loads(resp.body.decode('utf8', 'replace'))
    futures = []

    @coroutine
    def handle_server(user, server_name, server, max_age, inactive_limit):
        """Handle (maybe) culling a single server

        "server" is the entire server model from the API.

        Returns True if server is now stopped (user removable),
        False otherwise.
        """
        log_name = user['name']
        if server_name:
            log_name = '%s/%s' % (user['name'], server_name)
        if server.get('pending'):
            app_log.warning(
                "Not culling server %s with pending %s", log_name, server['pending']
            )
            return False

        # jupyterhub < 0.9 defined 'server.url' once the server was ready
        # as an *implicit* signal that the server was ready.
        # 0.9 adds a dedicated, explicit 'ready' field.
        # By current (0.9) definitions, servers that have no pending
        # events and are not ready shouldn't be in the model,
        # but let's check just to be safe.

        if not server.get('ready', bool(server['url'])):
            app_log.warning(
                "Not culling not-ready not-pending server %s: %s", log_name, server
            )
            return False

        if server.get('started'):
            age = now - parse_date(server['started'])
        else:
            # started may be undefined on jupyterhub < 0.9
            age = None

        # check last activity
        # last_activity can be None in 0.9
        if server['last_activity']:
            inactive = now - parse_date(server['last_activity'])
        else:
            # no activity yet, use start date
            # last_activity may be None with jupyterhub 0.9,
            # which introduces the 'started' field which is never None
            # for running servers
            inactive = age

        # CUSTOM CULLING TEST CODE HERE
        # Add in additional server tests here.  Return False to mean "don't
        # cull", True means "cull immediately", or, for example, update some
        # other variables like inactive_limit.
        #
        # Here, server['state'] is the result of the get_state method
        # on the spawner.  This does *not* contain the below by
        # default, you may have to modify your spawner to make this
        # work.  The `user` variable is the user model from the API.
        #
        # if server['state']['profile_name'] == 'unlimited'
        #     return False
        # inactive_limit = server['state']['culltime']

        should_cull = (
            inactive is not None and inactive.total_seconds() >= inactive_limit
        )
        if should_cull:
            app_log.info(
                "Culling server %s (inactive for %s)", log_name, format_td(inactive)
            )

        if max_age and not should_cull:
            # only check started if max_age is specified
            # so that we can still be compatible with jupyterhub 0.8
            # which doesn't define the 'started' field
            if age is not None and age.total_seconds() >= max_age:
                app_log.info(
                    "Culling server %s (age: %s, inactive for %s)",
                    log_name,
                    format_td(age),
                    format_td(inactive),
                )
                should_cull = True

        if not should_cull:
            app_log.debug(
                "Not culling server %s (age: %s, inactive for %s)",
                log_name,
                format_td(age),
                format_td(inactive),
            )
            return False

        resp = yield delete_server(user['name'], server_name, url, auth_header, fetch)
        if resp.code == 202:
            app_log.warning("Server %s is slow to stop", log_name)
            # return False to prevent culling user with pending shutdowns
            return False
        return True

    @coroutine
    def handle_user(user):
        """Handle one user.

        Create a list of their servers, and async exec them.  Wait for
        that to be done, and if all servers are stopped, possibly cull
        the user.
        """
        # shutdown servers first.
        # Hub doesn't allow deleting users with running servers.
        # jupyterhub 0.9 always provides a 'servers' model.
        # 0.8 only does this when named servers are enabled.
        if 'servers' in user:
            servers = user['servers']
        else:
            # jupyterhub < 0.9 without named servers enabled.
            # create servers dict with one entry for the default server
            # from the user model.
            # only if the server is running.
            servers = {}
            if user['server']:
                servers[''] = {
                    'last_activity': user['last_activity'],
                    'pending': user['pending'],
                    'url': user['server'],
                }
        server_futures = [
            handle_server(user, server_name, server, max_age, inactive_limit)
            for server_name, server in servers.items()
        ]
        results = yield multi(server_futures)

        # some servers are still running, cannot cull users
        still_alive = len(results) - sum(results)

        # we need to know if we want to renew the EOS ticket or not
        # therefore this part of the code needs to check if there are sessions alive
        if not cull_users:
            return not still_alive

        if still_alive:
            app_log.debug(
                "Not culling user %s with %i servers still alive",
                user['name'],
                still_alive,
            )
            return False

        should_cull = False
        if user.get('created'):
            age = now - parse_date(user['created'])
        else:
            # created may be undefined on jupyterhub < 0.9
            age = None

        # check last activity
        # last_activity can be None in 0.9
        if user['last_activity']:
            inactive = now - parse_date(user['last_activity'])
        else:
            # no activity yet, use start date
            # last_activity may be None with jupyterhub 0.9,
            # which introduces the 'created' field which is never None
            inactive = age

        should_cull = (
            inactive is not None and inactive.total_seconds() >= inactive_limit
        )
        if should_cull:
            app_log.info("Culling user %s (inactive for %s)", user['name'], inactive)

        if max_age and not should_cull:
            # only check created if max_age is specified
            # so that we can still be compatible with jupyterhub 0.8
            # which doesn't define the 'started' field
            if age is not None and age.total_seconds() >= max_age:
                app_log.info(
                    "Culling user %s (age: %s, inactive for %s)",
                    user['name'],
                    format_td(age),
                    format_td(inactive),
                )
                should_cull = True

        if not should_cull:
            app_log.debug(
                "Not culling user %s (created: %s, last active: %s)",
                user['name'],
                format_td(age),
                format_td(inactive),
            )
            return False

        yield delete_user(user['name'], url, auth_header, fetch)
        return True

    for user in users:
        futures.append((user['name'], handle_user(user)))

    for (name, f) in futures:
        try:
            result = yield f
        except Exception:
            app_log.exception("Error processing %s", name)
        else:
            if result:
                app_log.debug("Finished culling %s", name)
            else:
                if not disable_hooks: check_ticket(name)

@coroutine
def check_blocked_users(url, api_token, client_id, client_secret, auth_url, audience, authz_api_url):
    """Detect blocked users.

    Detect blocked users and cull their servers.
    """
    # Step 1: Get Token for Authorization Service APIs (no Token Exchange permissions - too powerful)
    token_req = HTTPRequest(
        url=auth_url,
        method="POST",
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        body="grant_type=client_credentials&client_id=%s&client_secret=%s&audience=%s"
            % (quote(client_id), quote(client_secret), quote(audience)),
    )

    client = AsyncHTTPClient()

    try:
        token_resp = yield client.fetch(token_req)
        token_data = json.loads(token_resp.body.decode("utf-8"))
        access_token = token_data["access_token"]
    except Exception:
        app_log.exception("Failed to get access token for blocked user check")
        return

    # Step 2: Get users of SWAN
    auth_header = {'Authorization': 'token %s' % api_token}
    req = HTTPRequest(url=url + '/users', headers=auth_header)

    try:
        resp = yield client.fetch(req)
        users = json.loads(resp.body.decode('utf8', 'replace'))
    except Exception:
        app_log.exception("Failed to get user list for blocked user check")
        return

    # Step 3: Check each user - Get their identity from the Authorization Service API using the obtained token as Bearer
    for user in users:
        app_log.info("Checking if user %s is blocked", user['name'])
        query = urlencode([("field", "upn"), ("field", "blocked")])
        id_url = f"{authz_api_url}/{quote(user['name'])}?{query}"
        id_req = HTTPRequest(
            url=id_url,
            headers={
                "Authorization": "Bearer %s" % access_token,
                "Accept": "text/plain",
            }
        )

        try:
            id_resp = yield client.fetch(id_req)
            identity_data = json.loads(id_resp.body.decode("utf-8")).get("data", {})
            is_blocked = identity_data.get("blocked")
        except HTTPClientError as e:
            if e.code == 404:
                app_log.info(f"User {user['name']} not found for blocked user check, skipping.")
                continue
            else:
                app_log.warning(f"Failed to check identity for {user['name']}: {e}")
                continue

        if is_blocked:
            app_log.warning("User %s is blocked. Terminating their sessions.", user['name'])

            # collect user's server
            if 'servers' in user:
                servers = user['servers']
            else:
                servers = {}
                if user.get('server'):
                    servers[''] = {
                        'last_activity': user.get('last_activity'),
                        'pending': user.get('pending'),
                        'url': user['server'],
                    }

            delete_futures = []
            for server_name in servers:
                delete_futures.append(
                    delete_server(user['name'], server_name, url, auth_header, client.fetch)
                )
            # wait for all delete requests to complete
            results = yield multi(delete_futures)

            for i, server_name in enumerate(servers):
                try:
                    resp = results[i]
                    if resp.code in (204, 202):
                        app_log.info("Deleted server '%s' for user %s", server_name, user['name'])
                    else:
                        app_log.warning("Unexpected response deleting server %s for user %s: %s",
                                        server_name, user['name'], resp.code)
                except Exception:
                    app_log.exception("Failed to delete server %s for user %s", server_name, user['name'])

            yield delete_user(user['name'], url, auth_header, client.fetch)
            return True

def main():
    define(
        'url',
        default=os.environ.get('JUPYTERHUB_API_URL'),
        help="The JupyterHub API URL",
    )
    define('timeout', default=600, help="The idle timeout (in seconds)")
    define(
        'cull_every',
        default=0,
        help="The interval (in seconds) for checking for idle servers to cull",
    )
    define(
        'max_age',
        default=0,
        help="The maximum age (in seconds) of servers that should be culled even if they are active",
    )
    define(
        'cull_users',
        default=False,
        help="""Cull users in addition to servers.
                This is for use in temporary-user cases such as tmpnb.""",
    )
    define(
        'concurrency',
        default=10,
        help="""Limit the number of concurrent requests made to the Hub.

                Deleting a lot of users at the same time can slow down the Hub,
                so limit the number of API requests we have outstanding at any given time.
                """,
    )
    define('hooks_dir', default="/srv/jupyterhub/culler", help="Path to the directory for the krb tickets script (check_ticket.sh)")
    define('disable_hooks', default=False, help="The user's home is a temporary scratch directory and we should not check krb tickets")
    define('auth_url', default='', help="URL to fetch CERN access token")
    define('auth_client_id', default=os.environ.get('AUTH_CLIENT_ID'), help="Client ID for blocked user check")
    define('auth_client_secret', default=os.environ.get('AUTH_CLIENT_SECRET'), help="Client secret for blocked user check")
    define('audience', default='', help="Audience for CERN access token")
    define('auth_check_interval', default=0, help="The interval (in seconds) for checking blocked users")
    define('authz_api_url', default='', help="URL to fetch user identity from authorization service")


    parse_command_line()
    if not options.cull_every:
        options.cull_every = options.timeout // 2
    api_token = os.environ['JUPYTERHUB_API_TOKEN']

    try:
        AsyncHTTPClient.configure("tornado.curl_httpclient.CurlAsyncHTTPClient")
    except ImportError as e:
        app_log.warning(
            "Could not load pycurl: %s\n"
            "pycurl is recommended if you have a large number of users.",
            e,
        )

    loop = IOLoop.current()
    cull = partial(
        cull_idle,
        url=options.url,
        api_token=api_token,
        inactive_limit=options.timeout,
        cull_users=options.cull_users,
        disable_hooks=options.disable_hooks,
        max_age=options.max_age,
        concurrency=options.concurrency,
    )
    # schedule first cull immediately
    # because PeriodicCallback doesn't start until the end of the first interval
    loop.add_callback(cull)
    # schedule periodic cull
    pc = PeriodicCallback(cull, 1e3 * options.cull_every)
    pc.start()

    blocked_check = partial(
        check_blocked_users,
        url=options.url,
        api_token=api_token,
        auth_url = options.auth_url,
        client_id=options.auth_client_id,
        client_secret=options.auth_client_secret,
        audience = options.audience,
        authz_api_url=options.authz_api_url,
    )
    # schedule first blocked user check
    loop.add_callback(blocked_check)
    # schedule periodic blocked user check
    pc_blocked = PeriodicCallback(blocked_check, 1e3 * options.auth_check_interval)
    pc_blocked.start()
    
    try:
        loop.start()
    except KeyboardInterrupt:
        pass
