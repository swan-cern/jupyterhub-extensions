"""CERN Specific Spawner class"""

import subprocess
import os
from dockerspawner import SystemUserSpawner
from tornado import gen


class CERNSpawner(SystemUserSpawner):

    @gen.coroutine
    def start(self, image=None):
        """Start the container and perform the operations necessary for mounting
        EOS.
        """
        username = self.user.name
        # Create a temporary home for the user.
        home_dir = "/home/%s" %username
        subprocess.call(["mkdir","-p", home_dir])
        subprocess.call(["chown", username, home_dir])

        tornadoFuture = super(CERNSpawner, self).start(
            image=image
        )

        def get_and_bind_ticket(dummy):
            # Temporary limitation
            allowed_users = map(lambda s: s[:-1], open(os.environ["AUTHUSERS"]).readlines())
            if not username in allowed_users: return
            resp = self.docker('inspect_container',self.container_id)
            if not resp:
                self.log.warn("Container not found")
            container = resp.result()
            container_pid = container['State']['Pid']
            self.log.debug("We are in CERNSpawner. Container requested by %s has pid %s.", username, container_pid)
            subprocess.call([os.environ["AUTHSCRIPT"], username, str(container_pid)])

        tornadoFuture.add_done_callback(get_and_bind_ticket)
        yield tornadoFuture
