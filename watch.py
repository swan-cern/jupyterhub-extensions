"""
Simple script to watch for changes in static asset source files and
rebuild the packages automatically.

This script also automatically rebuilds the frontend assets when
changes are detected (saving you from running `npm run build` manually).

By default, JupyterHub looks for static assets in the
`<sys.prefix>/share/jupyterhub/static` directory. This means that every time
a source file (e.g. JS or CSS) is changed, the corresponding package needs to be
built and installed again before JupyterHub can serve the updated files.

Since this is pretty annoying during development, this script creates symlinks
from the JupyterHub static assets directory to the source files in this repo.
That way, JupyterHub always serves the latest files without needing to
reinstall the packages.
"""
import subprocess
import sys
from pathlib import Path

import click
from watchfiles import watch, DefaultFilter


REPO_ROOT = Path(__file__).parent.resolve()
JUPYTER_STATIC_DIR = Path(sys.prefix) / "share/jupyterhub/static"

# A mapping between static directories and the output share folder
# For example swanhub installs into "share/jupyterhub/static/swan"
packages = {
    "KeyCloakAuthenticator/keycloackauthenticator": "keycloackauthenticator",
    "SwanCuller/swanculler": "swanculler",
    "SwanHub/swanhub": "swan",
    "SwanNotificationsService/swannotificationsservice": "swannotificationsservice",
    "SwanSpawner/swanspawner": "swanspawner",
}

def create_symlinks():
    """
    Create symlinks between source directories and the output share folder.
    """
    for pkg, share_dir in packages.items():
        path = JUPYTER_STATIC_DIR / share_dir

        # Remove existing directories/symlinks if present
        try:
            path.unlink(missing_ok=True)
        except IsADirectoryError:
            import shutil
            shutil.rmtree(path)

        # Create symlink from the source files to the share directory
        target = REPO_ROOT / pkg / "static"
        if target.exists():
            path.symlink_to(target, target_is_directory=True)


def watch_for_changes():
    """
    Watch for file changes in the package static directories and automatically
    rebuild assets.
    """
    existing_paths = [REPO_ROOT / pkg / "static" for pkg in packages.keys()]
    existing_paths = [p for p in existing_paths if p.exists()]

    # style.css is a generated file, ignore changes to it
    ignore_filter = DefaultFilter(ignore_paths=[REPO_ROOT / "SwanHub/swanhub/static/css/style.css"])

    click.secho("Watching for changes...", fg="green")
    for _ in watch(*existing_paths, watch_filter=ignore_filter):
        click.secho("Changes detected, rebuilding packages...", fg="yellow")
        for pkg in packages.keys():
            package_json = (REPO_ROOT / pkg / "../package.json").resolve()
            if package_json.exists():
                subprocess.run(
                    ["npm", "run", "build"], cwd=REPO_ROOT / pkg, check=True
                )
        click.secho("Watching for changes...", fg="green")


create_symlinks()
watch_for_changes()
