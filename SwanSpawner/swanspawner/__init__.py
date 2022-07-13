from .binderspawner_mixin import BinderSpawnerMixin
from .swanspawner import SwanSpawner


class SwanBinderSpawner(BinderSpawnerMixin, SwanSpawner):
    pass


__all__ = ["SwanBinderSpawner", "SwanSpawner"]
