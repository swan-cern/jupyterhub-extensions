
from jupyterhub.app import JupyterHub

from traitlets.config.configurable import SingletonConfigurable, Config
from traitlets import (
    Int,
    Unicode,
    Bool,
    default
)


class SpawnHandlersConfigs(SingletonConfigurable):
    """
        Singleton class where all the configurations are stored
    """

    software_source = 'software_source'

    builder = 'builder'

    builder_version = 'builder_version'

    repository = 'repository'

    lcg_rel_field = 'lcg'

    spark_cluster_field = 'clusters'

    user_script_env_field = 'scriptenv'

    file = 'file'

    user_interface = 'user_interface'

    use_jupyterlab_field = 'use-jupyterlab'

    use_tn_field = 'use-tn'

    customenv_special_type = 'customenv'

    tn_enabled = Bool(
        default_value=False,
        config=True,
        help="True if this SWAN deployment is exposed to the Technical Network."
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

    spawn_error_message = Unicode(
        default_value='Error spawning your session',
        config=True,
        help='Message to display when Spawn fails'
    )

    @default('config')
    def _config_default(self):
        # load application config by default
        if JupyterHub.initialized():
            return JupyterHub.instance().config
        else:
            return Config()
