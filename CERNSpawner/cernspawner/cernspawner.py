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
        tornadoFuture = super(CERNSpawner, self).start(
            image=image
        )

        def get_and_bind_ticket(pippo):
            # Temporary limitation
            if not self.user.name in ["dpiparo","etejedor"]: return
            resp = self.docker('inspect_container',self.container_id)
            if not resp:
                self.log.warn("Container not found")
            container = resp.result()
            container_pid = container['State']['Pid']
            self.log.debug("We are in CERNSpawner. Container requested by %s has pid %s.", self.user.name, container_pid)
            subprocess.call([os.environ["AUTHSCRIPT"], self.user.name, container_pid])

        tornadoFuture.add_done_callback(get_and_bind_ticket)
        yield tornadoFuture
