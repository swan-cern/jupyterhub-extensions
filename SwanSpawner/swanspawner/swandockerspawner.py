from .swanspawner import define_SwanSpawner_from
from dockerspawner import SystemUserSpawner


class SwanDockerSpawner(define_SwanSpawner_from(SystemUserSpawner)):
    pass
