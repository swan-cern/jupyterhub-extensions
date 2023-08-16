from .swanspawner import define_SwanSpawner_from
from dockerspawner import SystemUserSpawner

import os, subprocess
import time
import contextlib
import random
import psutil
import json

from traitlets import (
    Unicode,
    Bool,
    Int,
    Dict
)

from socket import (
    socket,
    SO_REUSEADDR,
    SOL_SOCKET,
)

class SwanDockerSpawner(define_SwanSpawner_from(SystemUserSpawner)):

    auth_script = Unicode(
        default_value='',
        config=True,
        help='Script to authenticate.'
    )

    hadoop_auth_script = Unicode(
        config=True,
        help='Script to authenticate with hadoop clusters.'
    )

    init_k8s_user = Unicode(
        config=True,
        help='Script to authenticate with k8s clusters.'
    )
    yarn_config_script = Unicode(
        default_value='/cvmfs/sft.cern.ch/lcg/etc/hadoop-confext/hadoop-setconf.sh',
        config=True,
        help='Path in CVMFS of the script to configure a YARN cluster.'
    )

    k8s_config_script = Unicode(
        default_value='/cvmfs/sft.cern.ch/lcg/etc/hadoop-confext/k8s-setconf.sh',
        config=True,
        help='Path in CVMFS of the script to configure a K8s cluster.'
    )

    spark_max_sessions = Int(
        default_value=1,
        config=True,
        help='Number of parallel Spark sessions per user session (container).'
    )

    spark_session_num_ports = Int(
        default_value=3,
        config=True,
        help='Number of ports opened per user session (container).'
    )

    spark_session_port_range_start = Int(
        default_value=5001,
        config=True,
        help='Start of the port range that is used by the user session (container).'
    )

    spark_session_port_range_end = Int(
        default_value=5300,
        config=True,
        help='End of the port range that is used by the user session (container).'
    )
    check_cvmfs_status = Bool(
        default_value=True,
        config=True,
        help="Check if CVMFS is accessible. It only works if CVMFS is mounted in the host (not the case in ScienceBox)."
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.offload = False

    def get_env(self):
        """
        Set base environmental variables important for docker spawner
        """
        env = super().get_env()

        username = self.user.name

        # Only dockerspawner has these vars, and for now is the only one that needs this code
        if hasattr(self, 'extra_host_config') and hasattr(self, 'extra_create_kwargs'):
            # Clear old state
            self.extra_host_config['port_bindings'] = {}
            self.extra_create_kwargs['ports'] = []

            if self.lcg_rel_field not in self.user_options:
                # session spawned via the API, in binder start notebook with jovyan user
                self.extra_create_kwargs['working_dir'] = "/home/jovyan"
                self.extra_create_kwargs['user'] = 'jovyan'
                self.extra_create_kwargs['command'] = ["jupyterhub-singleuser","--ip=0.0.0.0","--NotebookApp.default_url=/lab"]

            # Avoid overriding the default container output port, defined by the Spawner
            if not self.use_internal_ip:
                self.extra_host_config['port_bindings'][self.port] = (self.host_ip,)

            if self.offload:
                cluster = self.user_options[self.spark_cluster_field]
                env['SPARK_CLUSTER_NAME'] = cluster
                env['SPARK_USER'] = username
                env['MAX_MEMORY'] = self.user_options[self.user_memory]

                if cluster == 'k8s':
                    env['SPARK_CONFIG_SCRIPT'] = self.k8s_config_script
                else:
                    env['SPARK_CONFIG_SCRIPT'] = self.yarn_config_script

                if cluster == 'hadoop-nxcals':
                    env['SPARK_AUTH_REQUIRED'] = "true"
                else:
                    env['SPARK_AUTH_REQUIRED'] = "false"

                # Asks the OS for random ports to give them to Docker,
                # so that Spark can be exposed to the outside
                # Reserves the ports so that other processes don't use them
                # before Docker opens them
                spark_ports = []
                for _ in range(self.spark_session_num_ports * self.spark_max_sessions):
                    try:
                        reserved_port = self.get_reserved_port(self.spark_session_port_range_start,
                                                               self.spark_session_port_range_end)
                    except Exception as ex:
                        self.log.error("Error while allocating ports for Spark: %s", ex, exc_info=True)
                        raise RuntimeError("Error while allocating ports for Spark. Please try again.")
                    self.extra_host_config['port_bindings'][reserved_port] = reserved_port
                    self.extra_create_kwargs['ports'].append(reserved_port)
                    spark_ports.append(str(reserved_port))
                env["SPARK_PORTS"] = ",".join(spark_ports)

        return env

    async def start(self):
        """Perform the operations necessary for mounting
        EOS, GPU support, authenticating HDFS and authenticating spark clusters.
        """
        
        # default values when spawned via API (e.g binder)
        with open(self.options_form_config) as json_file:
            options_form_config_data = json.load(json_file)

        username = self.user.name
        platform = self.user_options.get(self.platform_field,options_form_config_data["options"][1]['platforms'][0]['value'])
        lcg_rel = self.user_options.get(self.lcg_rel_field,options_form_config_data["options"][1]["lcg"]["value"])
        cluster = self.user_options.get(self.spark_cluster_field,options_form_config_data["options"][1]['clusters'][0]['value'])
        cpu_quota = self.user_options.get(self.user_n_cores,int(options_form_config_data["options"][1]['cores'][0]['value']))
        mem_limit = self.user_options.get(self.user_memory,options_form_config_data["options"][1]['memory'][0]['value'] + 'G')

        try:
            start_time_configure_user = time.time()

            if not self.local_home and self.lcg_rel_field in self.user_options and self.auth_script:
                # When using CERNBox as home, obtain credentials for the user
                subprocess.call(['sudo', self.auth_script, username], timeout=60)
                self.log.debug("We are in SwanSpawner. Credentials for %s were requested.", username)

            if self.check_cvmfs_status and not os.path.exists(self.lcg_view_path):
                raise RuntimeError(
                    """
                    Could not initialize software stack, please <a href="https://cern.ch/ssb" target="_blank">check service status</a> or <a href="https://cern.service-now.com/service-portal/function.do?name=swan" target="_blank">report an issue</a>
                    """)

            if self.check_cvmfs_status and not os.path.exists(self.lcg_view_path + '/' + lcg_rel + '/' + platform):
                raise ValueError(
                    """
                    Configuration not available: please select other <b>Software stack</b> and <b>Platform</b>.
                    """)

            self.log_metric(
                self.user.name,
                self.this_host,
                ".".join(["configure_user", lcg_rel, cluster, "duration_sec"]),
                time.time() - start_time_configure_user)

            # If the user selects a Spark Cluster we need to generate a token to allow him in
            if self.offload:
                start_time_configure_spark = time.time()

                # If the user selects a Spark Cluster we need to generate some tokens
                # FIXME: Dont hardcode hadoop path, use hadoop_host_path and hadoop_container_path
                hadoop_host_path = '/spark/' + username
                hadoop_container_path = '/spark'

                # Ensure that env variables are properly cleared
                self.env.pop('WEBHDFS_TOKEN', None)
                self.env.pop('HADOOP_TOKEN_FILE_LOCATION', None)
                self.env.pop('KUBECONFIG', None)

                # Set authentication and authorization for the user
                if cluster == 'k8s':
                    subprocess.call([
                        'sudo',
                        self.init_k8s_user,
                        username
                    ], timeout=60)

                    # set location of user kubeconfig for Spark
                    if os.path.exists(hadoop_host_path + '/k8s-user.config'):
                        self.env['KUBECONFIG'] = hadoop_container_path + '/k8s-user.config'
                    else:
                        raise RuntimeError(
                            """
                            Problem connecting to Cloud Containers cluster. 
                            Please <a href="https://cern.service-now.com/service-portal/function.do?name=swan" target="_blank">report an issue</a>
                            """)

                    subprocess.call([
                        'sudo',
                        self.hadoop_auth_script,
                        'analytix',
                        username
                    ], timeout=60)

                    # Set default EOS krb5 cache location to hadoop container path for k8s
                    self.env['KRB5CCNAME'] = hadoop_container_path + '/krb5cc'
                else:
                    subprocess.call([
                        'sudo',
                        self.hadoop_auth_script,
                        cluster,
                            username
                    ], timeout=60)

                    # Set default location for krb5cc in tmp directory for yarn
                    self.env['KRB5CCNAME'] = '/tmp/krb5cc'

                # set location of hadoop token file and webhdfs token for Spark
                if os.path.exists(hadoop_host_path + '/hadoop.toks') and os.path.exists(hadoop_host_path + '/webhdfs.toks'):
                    self.env['HADOOP_TOKEN_FILE_LOCATION'] = hadoop_container_path + '/hadoop.toks'
                    with open(hadoop_host_path + '/webhdfs.toks', 'r') as webhdfs_token_file:
                        self.env['WEBHDFS_TOKEN'] = webhdfs_token_file.read()
                else:
                    if cluster == 'hadoop-nxcals':
                        raise ValueError(
                            """
                            Access to the NXCALS cluster is not granted. 
                            Please <a href="http://nxcals-docs.web.cern.ch/current/user-guide/data-access/nxcals-access-request/" target="_blank">request access</a>
                            """)
                    elif cluster == 'k8s':
                        # if there is no HADOOP_TOKEN_FILE or WEBHDFS_TOKEN with K8s we ignore (no HDFS access granted)
                        pass
                    else:
                        # yarn clusters require HADOOP_TOKEN_FILE and WEBHDFS_TOKEN containing YARN and HDFS tokens
                        raise ValueError(
                            """
                            Access to the Analytix cluster is not granted. 
                            Please <a href="https://cern.service-now.com/service-portal?id=sc_cat_item&name=access-cluster-hadoop&se=Hadoop-Service" target="_blank">request access</a>
                            """)

                self.log_metric(
                    self.user.name,
                    self.this_host,
                    ".".join(["configure_spark", lcg_rel, cluster, "duration_sec"]),
                    time.time() - start_time_configure_spark
                )

            # The bahaviour changes if this if dockerspawner or kubespawner
            # Due to dockerpy limitations in the current version, we cannot use --cpu to limit cpu.
            # This is an alternative (and old) way of doing it
            self.extra_host_config.update({
                'cpu_period': 100000,
                'cpu_quota': 100000 * cpu_quota
            })
            self.mem_limit = mem_limit

            # Enabling GPU for cuda stacks
            # Options to export nvidia device can be found in https://github.com/NVIDIA/nvidia-container-runtime#nvidia_require_
            if "cu" in lcg_rel:
                self.env[
                    'NVIDIA_VISIBLE_DEVICES'] = 'all'  # We are making visible all the devices, if the host has more that one can be used.
                self.env['NVIDIA_DRIVER_CAPABILITIES'] = 'compute,utility'
                self.env['NVIDIA_REQUIRE_CUDA'] = 'cuda>=10.0 driver>=410'
                self.extra_host_config.update({'runtime': 'nvidia'})

            # start configured container
            startup = await super().start()

            return startup
        except BaseException as e:
            self.log.error("Error while spawning the user container: %s", e, exc_info=True)
            raise e

    @staticmethod
    def get_reserved_port(start, end, n_tries=10):
        """
            Reserve a random available port.
            It puts the door in TIME_WAIT state so that no other process gets it when asking for a random port,
            but allows processes to bind to it, due to the SO_REUSEADDR flag.
            From https://github.com/Yelp/ephemeral-port-reserve
        """
        for i in range(n_tries):
            try:
                with contextlib.closing(socket()) as s:
                    port = random.randint(start, end)
                    net_connections = psutil.net_connections()
                    # look through the list of active connections to check if the port is being used or not and return FREE if port is unused
                    if next((conn.laddr[1] for conn in net_connections if conn.laddr[1] == port), 'FREE') != 'FREE':
                        raise Exception('Port {} is in use'.format(port))
                    s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
                    s.bind(('127.0.0.1', port))

                    # the connect below deadlocks on kernel >= 4.4.0 unless this arg is greater than zero
                    s.listen(1)

                    sockname = s.getsockname()

                    # these three are necessary just to get the port into a TIME_WAIT state
                    with contextlib.closing(socket()) as s2:
                        s2.connect(sockname)
                        s.accept()
                        return sockname[1]
            except:
                if i == n_tries - 1:
                    raise
