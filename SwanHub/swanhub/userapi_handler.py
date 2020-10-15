
from jupyterhub.apihandlers.base import APIHandler
from tornado import web
import json


class SelfAPIHandler(APIHandler):
    """
        Handler for the user api endpoint.
        This allows us to force the visibility of the auth state


        Return the authenticated user's model
        Based on the authentication info. Acts as a 'whoami' for auth tokens.
    """

    async def get(self):
        user = self.current_user
        if user is None:
            # whoami can be accessed via oauth token
            user = self.get_current_user_oauth_token()
        if user is None:
            raise web.HTTPError(403)

        model = self.user_model(user)
        model['auth_state'] = await user.get_auth_state()
        self.write(json.dumps(model))