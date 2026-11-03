"""Script to periodically refresh Kerberos tokens for SWAN sessions"""

import os
from functools import partial
from subprocess import call

from tornado.escape import json_decode
from tornado.httpclient import AsyncHTTPClient
from tornado.ioloop import IOLoop, PeriodicCallback
from tornado.log import app_log
from tornado.options import define, options, parse_command_line


def check_ticket(username):
    app_log.info("Checking ticket for user %s", username)
    call(["sudo", "--preserve-env=SWAN_DEV", "%s/check_ticket.sh" % options.hooks_dir, username])


async def check_tickets(url, api_token):
    """Check & refresh tickets for all users with an open session"""
    headers = {
        "Authorization": f"token {api_token}",
        "Accept": "application/jupyterhub-pagination+json",
    }
    next_url = f"{url}/users?state=active"
    client = AsyncHTTPClient()
    users = []
    while next_url:
        resp = await client.fetch(next_url, headers=headers)
        page = json_decode(resp.body)

        users.extend(page["items"])

        next_page_info = page["_pagination"]["next"]
        next_url = next_page_info["url"] if next_page_info else None

    for user in users:
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
