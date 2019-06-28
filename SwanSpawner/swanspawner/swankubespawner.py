from .swanspawner import define_SwanSpawner_from
from kubespawner import KubeSpawner


class SwanKubeSpawner(define_SwanSpawner_from(KubeSpawner)):
    pass