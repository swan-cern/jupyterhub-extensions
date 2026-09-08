import os

# swanspawner/__init__.py skips the kubernetes spawner import in dev mode,
# preventing an in-cluster config load during test collection.
os.environ.setdefault("SWANHUB_ENV", "dev")
