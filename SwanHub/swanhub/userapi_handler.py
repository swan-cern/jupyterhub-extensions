
from jupyterhub.apihandlers.base import APIHandler
from jupyterhub.scopes import identify_scopes as scopes_identify_scopes, parse_scopes
from jupyterhub.orm import Service as orm_Service
from tornado import web
import json


class SelfAPIHandler(APIHandler):
    """
        Handler for the user api endpoint.
        This allows us to force the visibility of the auth state

        FIXME this is no longer needed, as the RBAC system allows us to get the auth_state
        from `/api/users/<username>`.
        But this change was kept to also allow the auth_state from `/api/user`, thus
        making it compatible across k8s (running this new version) and puppet (running the old JH version).
        Once puppet is removed, we can remove this code and update SwanOauthRenew


        Return the authenticated user's model
        Based on the authentication info. Acts as a 'whoami' for auth tokens.
    """

    async def get(self):
        user = self.current_user
        if user is None:
            raise web.HTTPError(403)

        _added_scopes = set()
        if isinstance(user, orm_Service):
            # ensure we have the minimal 'identify' scopes for the token owner
            identify_scopes = scopes_identify_scopes(user)
            get_model = self.service_model
        else:
            identify_scopes = scopes_identify_scopes(user.orm_user)
            get_model = self.user_model

        # ensure we have permission to identify ourselves
        # all tokens can do this on this endpoint
        for scope in identify_scopes:
            if scope not in self.expanded_scopes:
                _added_scopes.add(scope)
                self.expanded_scopes |= {scope}
        if _added_scopes:
            # re-parse with new scopes
            self.parsed_scopes = parse_scopes(self.expanded_scopes)

        model = get_model(user)

        # add session_id associated with token
        # added in 2.0
        token = self.get_token()
        if token:
            model["session_id"] = token.session_id
        else:
            model["session_id"] = None

        # add scopes to identify model,
        # but not the scopes we added to ensure we could read our own model
        model["scopes"] = sorted(self.expanded_scopes.difference(_added_scopes))
        # SWAN the line bellow was added
        model['auth_state'] = await user.get_auth_state()
        self.write(json.dumps(model))