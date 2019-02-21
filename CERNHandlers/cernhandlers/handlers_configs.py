
from jupyterhub.app import JupyterHub

from traitlets.config.configurable import SingletonConfigurable, Config
from traitlets import (
    Unicode,
    Bool,
    default
)


class SpawnHandlersConfigs(SingletonConfigurable):
    """
        Singleton class where all the configurations are stored
    """

    swanrc_path = Unicode(
        default_value='/srv/jupyterhub/swanrc/swanrc.sh',
        config=True,
        help='Path of the bash script to read and write user swanrc file'
    )

    local_home = Bool(
        default_value=False,
        config=True,
        help="If True, a physical directory on the host will be the home and not eos."
    )

    maintenance_file = Unicode(
        default_value='/etc/nologin',
        config=True,
        help='Path of the file that, when present, enables maintenance mode'
    )

    notifications_file = Unicode(
        default_value='/srv/jupyterhub/notifications.json',
        config=True,
        help='Path of json file where the notifications to the users are written'
    )

    @default('config')
    def _config_default(self):
        # load application config by default
        if JupyterHub.initialized():
            return JupyterHub.instance().config
        else:
            return Config()
