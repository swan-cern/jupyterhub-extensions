
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

    builder = 'builder'
    
    builder_version = 'builder_version'
            
    repository_type = 'repository_type'

    repository = 'repository'

    notebook = 'notebook'

    lcg_rel_field = 'LCG-rel'

    platform_field = 'platform'

    user_script_env_field = 'scriptenv'

    user_n_cores = 'ncores'

    user_memory = 'memory'

    spark_cluster_field = 'spark-cluster'

    condor_pool = 'condor-pool'

    customenv_special_type = 'customenv'

    accpy_special_type = 'accpy'

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
