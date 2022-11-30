from . import BinderSpawnerMixin, SwanSpawner


class SwanBinderSpawner(BinderSpawnerMixin, SwanSpawner):
    pass


__all__ = ["SwanBinderSpawner", "SwanSpawner"]
