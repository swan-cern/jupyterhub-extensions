
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

    source_type = 'source_type'

    customenv_type = 'customenv_type'
    
    customenv_type_version = 'customenv_type_version'
            
    repository_type = 'repository_type'

    repository = 'repository'

    lcg_rel_field = 'LCG-rel'

    platform_field = 'platform'

    user_script_env_field = 'scriptenv'

    user_n_cores = 'ncores'

    user_memory = 'memory'

    spark_cluster_field = 'spark-cluster'

    condor_pool = 'condor-pool'

    eos_pattern = Unicode(
        default_value=r'^(?:\$CERNBOX|(?:/[^/\n]+)*/[^/\n]+)?$',
        config=True,
        help='Regular expression pattern for the repository provided by a EOS folder.'
    )

    eos_special_type = Unicode(
        default_value='eos',
        config=True,
        help='Special type for the repository provided by a EOS folder.'
    )

    git_pattern = Unicode(
        default_value=r'https?://(?:github\.com|gitlab\.cern\.ch)/([^/\s]+)/([^/\s]+)/?',
        config=True,
        help='Regular expression pattern for the repository provided by a GitLab or GitHub repository.'
    )

    git_special_type = Unicode(
        default_value='git',
        config=True,
        help='Special repository type for Git repositories.'
    )

    lcg_special_type = Unicode(
        default_value='lcg',
        config=True,
        help='Special type for default sourcing.'
    )

    customenv_special_type = Unicode(
        default_value='customenv',
        config=True,
        help='Special type for sourcing the environment.'
    )

    accpy_special_type = Unicode(
        default_value='accpy',
        config=True,
        help='Special type for custom environments.'
    )

    env_name = Unicode(
        default_value='{project_folder}_env',
        config=True,
        help='Name format for custom environment launched by the user.'
    )

    default_platform = Unicode(
        default_value='x86_64-el9-gcc13-opt',
        config=True,
        help='Default platform configuration for LCG views.'
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

    graphite_metric_path = Unicode(
        default_value='c5.swan',
        config=True,
        help='Base path for SWAN in Grafana metrics'
    )

    graphite_server = Unicode(
        default_value='filer-carbon.cern.ch',
        config=True,
        help='Server where to post the metrics collected'
    )

    graphite_server_port_batch = Int(
        default_value=2004,
        config=True,
        help='Port of the server where to post the metrics collected'
    )

    metrics_on = Bool(
        default_value=True,
        config=True,
        help="If True, it will send the metrics to CERN grafana (temporary, we will separate the metrics from the spwaner)."
    )

    @default('config')
    def _config_default(self):
        # load application config by default
        if JupyterHub.initialized():
            return JupyterHub.instance().config
        else:
            return Config()
