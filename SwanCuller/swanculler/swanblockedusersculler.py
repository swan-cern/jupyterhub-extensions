"""Script to check for blocked users and cull their servers."""

import json
import os
from functools import partial

try:
    from urllib.parse import quote, urlencode
except ImportError:
    from urllib import quote, urlencode

from tornado.gen import coroutine, multi
from tornado.httpclient import AsyncHTTPClient, HTTPClientError, HTTPRequest
from tornado.ioloop import IOLoop, PeriodicCallback
from tornado.locks import Semaphore
from tornado.log import app_log
from tornado.options import define, options, parse_command_line


@coroutine
def delete_server(user_name, server_name, url, auth_header, fetch):
    if server_name:
        # culling a named server
        delete_url = url + "/users/%s/servers/%s" % (
            quote(user_name),
            quote(server_name),
        )
    else:
        delete_url = url + "/users/%s/server" % quote(user_name)

    req = HTTPRequest(url=delete_url, method="DELETE", headers=auth_header)
    resp = yield fetch(req)
    return resp


@coroutine
def delete_user(user_name, url, auth_header, fetch):
    req = HTTPRequest(url=url + "/users/%s" % user_name, method="DELETE", headers=auth_header)
    resp = yield fetch(req)
    return resp


@coroutine
def check_blocked_users(url, api_token, client_id, client_secret, auth_url, audience, authz_api_url, concurrency=10):
    """Detect blocked users.

    Detect blocked users and cull both their servers and the user.
    """
    # Step 0: Get users from JupyterHub API
    auth_header = {"Authorization": "token %s" % api_token}
    req = HTTPRequest(url=url + "/users", headers=auth_header)
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

    users = json.loads(resp.body.decode("utf8", "replace"))

    # Step 1: Get Token for Authorization Service APIs (no Token Exchange permissions - too powerful)
    token_req = HTTPRequest(
        url=auth_url,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body="grant_type=client_credentials&client_id=%s&client_secret=%s&audience=%s"
        % (quote(client_id), quote(client_secret), quote(audience)),
    )

    try:
        token_resp = yield fetch(token_req)
        token_data = json.loads(token_resp.body.decode("utf-8"))
        access_token = token_data["access_token"]
    except Exception:
        app_log.exception("Failed to get access token for blocked user check")
        return

    # Step 2: Check each user - Get their identity from the Authorization Service API using the obtained token as Bearer
    @coroutine
    def handle_user(user):
        app_log.info("Checking if user %s is blocked", user["name"])
        query = urlencode([("field", "uniqueIdentifier"), ("field", "blocked"), ("field", "disabled")])
        id_url = f"{authz_api_url}/{quote(user['name'])}/accounts?{query}"
        id_req = HTTPRequest(
            url=id_url,
            headers={
                "Authorization": "Bearer %s" % access_token,
                "Accept": "*/*",
            },
        )

        try:
            id_resp = yield fetch(id_req)
            data = json.loads(id_resp.body.decode("utf-8")).get("data", [])
            if not data:
                app_log.warning(f"No identity data returned for user {user['name']}")
                return
            is_blocked = data[0].get("blocked", False)
            is_disabled = data[0].get("disabled", False)
        except HTTPClientError as e:
            if e.code == 404:
                app_log.info(f"User {user['name']} not found for blocked user check, skipping.")
                return
            else:
                app_log.warning(f"Failed to check identity for {user['name']}: {e}")
                return

        if is_blocked or is_disabled:
            app_log.warning("User %s is blocked. Terminating their sessions.", user["name"])
            auth_header = {"Authorization": "token %s" % api_token}

            # collect user's server
            if "servers" in user:
                servers = user["servers"]
            else:
                servers = {}
                if user.get("server"):
                    servers[""] = {
                        "last_activity": user.get("last_activity"),
                        "pending": user.get("pending"),
                        "url": user["server"],
                    }

            delete_futures = []
            for server_name in servers:
                delete_futures.append(delete_server(user["name"], server_name, url, auth_header, fetch))
            # wait for all delete requests to complete
            results = yield multi(delete_futures)

            for i, server_name in enumerate(servers):
                try:
                    resp = results[i]
                    if resp.code in (204, 202):
                        app_log.info("Deleted server '%s' for user %s", server_name, user["name"])
                    else:
                        app_log.warning(
                            "Unexpected response deleting server %s for user %s: %s",
                            server_name,
                            user["name"],
                            resp.code,
                        )
                except Exception:
                    app_log.exception("Failed to delete server %s for user %s", server_name, user["name"])

            yield delete_user(user["name"], url, auth_header, fetch)

    futures = []
    for user in users:
        futures.append((user["name"], handle_user(user)))

    for name, f in futures:
        try:
            yield f
        except Exception:
            app_log.exception("Error processing %s", name)


def main():
    define(
        "url",
        default=os.environ.get("JUPYTERHUB_API_URL"),
        help="The JupyterHub API URL",
    )
    define(
        "concurrency",
        default=10,
        help="""Limit the number of concurrent requests made to the Hub.

                Deleting a lot of users at the same time can slow down the Hub,
                so limit the number of API requests we have outstanding at any given time.
                """,
    )
    define("auth_url", default="", help="URL to fetch CERN access token")
    define("auth_client_id", default=os.environ.get("AUTH_CLIENT_ID"), help="Client ID for blocked user check")
    define(
        "auth_client_secret", default=os.environ.get("AUTH_CLIENT_SECRET"), help="Client secret for blocked user check"
    )
    define("audience", default="", help="Audience for CERN access token")
    define("auth_check_interval", default=14400, help="The interval (in seconds) for checking blocked users")
    define("authz_api_url", default="", help="URL to fetch user identity from authorization service")

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
    blocked_check = partial(
        check_blocked_users,
        url=options.url,
        api_token=api_token,
        auth_url=options.auth_url,
        client_id=options.auth_client_id,
        client_secret=options.auth_client_secret,
        audience=options.audience,
        authz_api_url=options.authz_api_url,
        concurrency=options.concurrency,
    )
    # schedule first blocked user check
    # because PeriodicCallback doesn't start until the end of the first interval
    loop.add_callback(blocked_check)
    # schedule periodic blocked user check
    pc_blocked = PeriodicCallback(blocked_check, 1e3 * options.auth_check_interval)
    pc_blocked.start()

    try:
        loop.start()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
