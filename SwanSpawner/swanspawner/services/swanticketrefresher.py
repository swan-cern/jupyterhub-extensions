"""Script to periodically refresh Kerberos tokens for SWAN sessions"""

import json
import os
from functools import partial
from subprocess import call

from tornado.gen import coroutine
from tornado.httpclient import AsyncHTTPClient, HTTPRequest
from tornado.ioloop import IOLoop, PeriodicCallback
from tornado.log import app_log
from tornado.options import define, options, parse_command_line


def check_ticket(username):
    app_log.info("Checking ticket for user %s", username)
    call(["sudo", "--preserve-env=SWAN_DEV", "%s/check_ticket.sh" % options.hooks_dir, username])


@coroutine
def check_tickets(url, api_token):
    """Check & refresh tickets for all users with an open session"""
    auth_header = {"Authorization": "token %s" % api_token}
    req = HTTPRequest(url=url + "/users", headers=auth_header)
    client = AsyncHTTPClient()

    resp = yield client.fetch(req)

    users = json.loads(resp.body.decode("utf8", "replace"))

    for user in users:
        if user.get("servers", {}) or "server" in user:
            check_ticket(user["name"])


def main():
    define(
        "url",
        default=os.environ.get("JUPYTERHUB_API_URL"),
        help="The JupyterHub API URL",
    )
    define(
        "every",
        default=600,
        help="The interval (in seconds) for checking tickets",
    )
    define(
        "hooks_dir",
        default="/srv/jupyterhub/culler",
        help="Path to the directory for the krb tickets script (check_ticket.sh)",
    )

    parse_command_line()
    api_token = os.environ["JUPYTERHUB_API_TOKEN"]

    try:
        AsyncHTTPClient.configure("tornado.curl_httpclient.CurlAsyncHTTPClient")
    except ImportError as e:
        app_log.warning(
            "Could not load pycurl: %s\npycurl is recommended if you have a large number of users.",
            e,
        )

    loop = IOLoop.current()
    check = partial(
        check_tickets,
        url=options.url,
        api_token=api_token,
    )
    # schedule first check immediately
    # because PeriodicCallback doesn't start until the end of the first interval
    loop.add_callback(check)
    # schedule periodic check
    pc = PeriodicCallback(check, 1e3 * options.every)
    pc.start()

    try:
        loop.start()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
