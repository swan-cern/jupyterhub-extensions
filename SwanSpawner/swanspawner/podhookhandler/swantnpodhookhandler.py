from .swanlabelpodhookhandler import SwanLabelPodHookHandler

"""
Class handling KubeSpawner.modify_pod_hook(spawner,pod) call

Perform Technical Network checks.
"""


class SwanTNPodHookHandler(SwanLabelPodHookHandler):
    async def get_swan_user_pod(self):
        await super().get_swan_user_pod()

        # Check if the user has access to the Technical Network
        self._check_tn_access()

        return self.pod

    def _check_tn_access(self):
        """
        Helper function to check if this SWAN deployment is exposed to the Technical Network
        and, if so, validate if the user has access to it.
        """
        user_roles = self.spawner.user_roles
        ats_role = self.spawner.ats_role
        tn_enabled = self.spawner.tn_enabled

        if tn_enabled and ats_role not in user_roles:
            raise ValueError("Access to the Technical Network is not granted.")
