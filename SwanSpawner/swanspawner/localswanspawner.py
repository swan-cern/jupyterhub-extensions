from jupyterhub.spawner import SimpleLocalProcessSpawner

from swanspawner.swanspawner import define_SwanSpawner_from


class LocalSwanSpawner(define_SwanSpawner_from(SimpleLocalProcessSpawner)):
    """A SwanSpawner variant for local process spawning (for testing/development)."""

    def get_env(self):
        # Skip SwanSpawnwer.get_env which is incompatible with SimpleLocalProcessSpawner
        return SimpleLocalProcessSpawner.get_env(self)
