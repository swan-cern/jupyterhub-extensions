# Author: Danilo Piparo, Enric Tejedor, Diogo Castro 2015
# Copyright CERN

"""CERN Specific Spawner class"""

import os
import pwd
import subprocess
from tornado import gen
from traitlets import (
    Unicode,
    Bool,
    Int,
    List,
    Dict
)

import contextlib
from socket import (
    socket,
    SO_REUSEADDR,
    SOL_SOCKET,
    gethostname
)


def define_SwanSpawner_from(base_class):
    """
        The Spawner need to inherit from a proper upstream Spawner (i.e Docker or Kube).
        But since our personalization, added on top of those, is exactly the same for all,
        by allowing a dynamic inheritance we can re-use the same code on all cases.
        This function returns our SwanSpawner, inheriting from a class (upstream Spawner)
        given as parameter.
    """

    class SwanSpawner(base_class):

        lcg_view_path = Unicode(
            default_value='/cvmfs/sft.cern.ch/lcg/views',
            config=True,
            help='Path where LCG views are stored in CVMFS.'
        )

        lcg_rel_field = Unicode(
            default_value='LCG-rel',
            help='LCG release field of the Spawner form.'
        )

        platform_field = Unicode(
            default_value='platform',
            help='Platform field of the Spawner form.'
        )

        user_script_env_field = Unicode(
            default_value='scriptenv',
            help='User environment script field of the Spawner form.'
        )

        user_n_cores = Unicode(
            default_value='ncores',
            help='User number of cores field of the Spawner form.'
        )

        user_memory = Unicode(
            default_value='memory',
            help='User available memory field of the Spawner form.'
        )

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

        local_home = Bool(
            default_value=False,
            config=True,
            help="If True, a physical directory on the host will be the home and not eos."
        )

        eos_path_prefix = Unicode(
            default_value='/eos/user',
            config=True,
            help='Path in eos preceeding the /t/theuser directory (e.g. /eos/user, /eos/scratch/user).'
        )

        spark_config_script = Unicode(
            default_value='/cvmfs/sft.cern.ch/lcg/etc/hadoop-confext/hadoop-setconf.sh',
            config=True,
            help='Path in CVMFS of the script to configure a Spark cluster.'
        )

        spark_cluster_field = Unicode(
            default_value='spark-cluster',
            help='Spark cluster name field of the Spawner form.'
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

        available_cores = List(
            default_value=['1'],
            config=True,
            help='List of cores options available to the user'
        )

        available_memory = List(
            default_value=['8'],
            config=True,
            help='List of memory options available to the user'
        )

        graphite_metric_path = Unicode(
            default_value='c5.swan',
            config=True,
            help='Base path for SWAN in Grafana metrics'
        )

        graphite_base_path = Unicode(
            default_value='spawn_form',
            config=True,
            help='Base path for the metrics generated in this object'
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

        shared_volumes = Dict(
            config=True,
            help='Volumes to be mounted with a "shared" tag. This allows mount propagation.',
        )

        extra_env = Dict(
            config=True,
            help='Extra environment variables to pass to the container',
        )

        image_slc6 = Unicode(
            config=True,
            help='TEMPORARY: SLC6 image to spawn a session'
        )

        metrics_on = Bool(
            default_value=True,
            config=True,
            help="If True, it will send the metrics to CERN grafana (temporary, we will separate the metrics from the spwaner)."
        )


        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.offload = False
            self.this_host = gethostname().split('.')[0]

        def options_from_form(self, formdata):
            options = {}
            options[self.lcg_rel_field]         = formdata[self.lcg_rel_field][0]
            options[self.platform_field]        = formdata[self.platform_field][0]
            options[self.user_script_env_field] = formdata[self.user_script_env_field][0]
            options[self.spark_cluster_field]   = formdata[self.spark_cluster_field][0] if self.spark_cluster_field in formdata.keys() else 'none'
            options[self.user_n_cores]          = int(formdata[self.user_n_cores][0]) if formdata[self.user_n_cores][0] in self.available_cores else int(self.available_cores[0])
            options[self.user_memory]           = formdata[self.user_memory][0] + 'g' if formdata[self.user_memory][0] in self.available_memory else self.available_memory[0] + 'g'

            self.offload = options[self.spark_cluster_field] != 'none'

            return options

        def get_env(self):
            """
            Set base environmental variables
            """
            env = super().get_env()

            username = self.user.name
            userid = pwd.getpwnam(username).pw_uid
            if self.local_home:
                homepath = "/scratch/%s" %(username)
            else:
                homepath = "%s/%s/%s" %(self.eos_path_prefix, username[0], username)

            env.update(dict(
                ROOT_LCG_VIEW_NAME     = self.user_options[self.lcg_rel_field],
                ROOT_LCG_VIEW_PLATFORM = self.user_options[self.platform_field],
                USER_ENV_SCRIPT        = self.user_options[self.user_script_env_field],
                ROOT_LCG_VIEW_PATH     = self.lcg_view_path,
                USER                   = username,
                USER_ID                = str(userid),
                HOME                   = homepath,

                JPY_USER               = self.user.name,
                JPY_COOKIE_NAME        = self.user.server.cookie_name,
                JPY_BASE_URL           = self.user.base_url,
                JPY_HUB_PREFIX         = self.hub.base_url,
                JPY_HUB_API_URL        = self.hub.api_url
            ))

            if self.extra_env:
                env.update(self.extra_env)

            # Clear old state
            self.extra_host_config['port_bindings'] = {}
            self.extra_create_kwargs['ports'] = []

            # Avoid overriding the default container output port, defined by the Spawner
            if not self.use_internal_ip:
                self.extra_host_config['port_bindings'][self.port] = (self.host_ip,)

            if self.offload:
                cluster = self.user_options[self.spark_cluster_field]
                env['SPARK_CLUSTER_NAME'] 		    = cluster
                env['SPARK_USER'] 		            = username
                env['SERVER_HOSTNAME']   	 	    = os.uname().nodename
                env['MAX_MEMORY']         	   	    = self.user_options[self.user_memory]

                env['SPARK_CONFIG_SCRIPT'] = self.spark_config_script

                # Asks the OS for random ports to give them to Docker,
                # so that Spark can be exposed to the outside
                # Reserves the ports so that other processes don't use them
                # before Docker opens them
                spark_ports = []
                for _ in range(self.spark_session_num_ports * self.spark_max_sessions):
                    try:
                        reserved_port =  self.get_reserved_port()
                    except Exception as ex:
                        self.log.error("Error while allocating ports for Spark: %s", ex, exc_info=True)
                        raise RuntimeError("Error while allocating ports for Spark. Please try again.")
                    self.extra_host_config['port_bindings'][reserved_port] = reserved_port
                    self.extra_create_kwargs['ports'].append(reserved_port)
                    spark_ports.append(str(reserved_port))
                env["SPARK_PORTS"] = ",".join(spark_ports)

            return env

        @gen.coroutine
        def start(self):
            """Start the container and perform the operations necessary for mounting
            EOS, authenticating HDFS and authenticating K8S.
            """

            username = self.user.name
            platform = self.user_options[self.platform_field]
            lcg_rel = self.user_options[self.lcg_rel_field]
            cluster = self.user_options[self.spark_cluster_field]
            cpu_quota = self.user_options[self.user_n_cores]
            mem_limit = self.user_options[self.user_memory]

            if not self.local_home and self.auth_script:
                # When using CERNBox as home, obtain credentials for the user
                subprocess.call(['sudo', self.auth_script, username])
                self.log.debug("We are in SwanSpawner. Credentials for %s were requested.", username)

            # If the user selects a Spark Cluster we need to generate a token to allow him in
            if self.offload:
                # FIXME: temporaly limit Cloud Container to specific platform and software stack
                if cluster == 'k8s' and "dev" not in lcg_rel:
                    raise ValueError(
                        "Configuration unsupported: "
                        "only <b>Software stack: Bleeding Edge</b> is supported for Cloud Containers"
                    )

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
                        username,
                        hadoop_host_path + '/k8s-user.config'
                    ])

                    # set location of user kubeconfig for Spark
                    if os.path.exists(hadoop_host_path + '/k8s-user.config'):
                        self.env['KUBECONFIG'] = hadoop_container_path + '/k8s-user.config'
                    else:
                        raise ValueError(
                            """
                            Access to the selected K8s cluster is not granted. 
                            Please <a href="https://cern.service-now.com/service-portal/function.do?name=swan" target="_blank">request access</a>
                            """
                        )

                    # Set default EOS krb5 cache location to hadoop container path for k8s
                    self.env['KRB5CCNAME'] = hadoop_container_path + '/krb5cc'
                else:
                    subprocess.call([
                        'sudo',
                        self.hadoop_auth_script ,
                        self.lcg_view_path + '/' + lcg_rel + '/' + platform,
                        cluster,
                        username
                    ])

                    # read the generated webhdfs token from host into env variable used by Spark
                    if os.path.exists(hadoop_host_path + '/webhdfs.toks'):
                        with open(hadoop_host_path + '/webhdfs.toks', 'r') as webhdfs_token_file:
                            self.env['WEBHDFS_TOKEN'] = webhdfs_token_file.read()
                    else:
                        raise ValueError(
                            """
                            Access to the selected YARN cluster is not granted. 
                            Please <a href="https://cern.service-now.com/service-portal/report-ticket.do?name=request&se=Hadoop-Service" target="_blank">request access</a>
                            """
                        )

                    # set location of hadoop token file for Spark
                    if os.path.exists(hadoop_host_path + '/hadoop.toks'):
                        self.env['HADOOP_TOKEN_FILE_LOCATION'] = hadoop_container_path + '/hadoop.toks'
                    else:
                        if cluster == 'nxcals':
                            raise ValueError(
                                """
                                Access to the NXCALS cluster is not granted. 
                                Please <a href="https://wikis.cern.ch/display/NXCALS/Data+Access+User+Guide#DataAccessUserGuide-nxcals_access" target="_blank">request access</a>
                                """
                            )
                        else:
                            raise ValueError(
                                """
                                Access to the selected YARN cluster is not granted. 
                                Please <a href="https://cern.service-now.com/service-portal/report-ticket.do?name=request&se=Hadoop-Service" target="_blank">request access</a>
                                """
                            )

                    # Set default location for krb5cc in tmp directory for yarn
                    self.env['KRB5CCNAME'] = '/tmp/krb5cc'

            # Due to dockerpy limitations in the current version, we cannot use --cpu to limit cpu.
            # This is an alternative (and old) way of doing it
            self.extra_host_config.update({
                'cpu_period' : 100000,
                'cpu_quota' : 100000 * cpu_quota,
                'mem_limit' : mem_limit
            })

            # Temporary fix to have both slc6 and cc7 image available. It should be removed
            # as soon as we move to cc7 completely.
            if "slc6" in self.user_options[self.platform_field]:
                self.image = self.image_slc6

            try:
                if self.metrics_on:
                    self.send_metrics()
            except Exception as ex:
                self.log.error("Failed to send metrics: %s", ex, exc_info=True)

            startup = yield super().start()
            return startup

        @property
        def volume_mount_points(self):
            """
            Override this method to take into account the "shared" volumes.
            """
            return self.get_volumes(only_mount=True)


        @property
        def volume_binds(self):
            """
            Since EOS now uses autofs (mounts and unmounts mount points automatically), we have to mount
            eos in the container with the propagation option set to "shared".
            This means that: when users try to access /eos/projects, the endpoint will be mounted automatically,
            and made available in the container without the need to restart the session (it gets propagated).
            This also means that, if the user endpoint fails, when it gets back up it will be made available in
            the container without the need to restart the session.
            The Spawnwer/dockerpy do not support this option. But, if volume_bins return a list of string, they will
            pass the list forward until the container construction, without checking or trying to manipulate the list.
            """
            return self.get_volumes()

        def get_volumes(self, only_mount=False):

            def _fmt(v):
                return self.format_volume_name(v, self)

            def _convert_list(volumes, binds, mode="rw"):
                for k, v in volumes.items():
                    m = mode
                    if isinstance(v, dict):
                        if "mode" in v:
                            m = v["mode"]
                        v = v["bind"]

                    if only_mount:
                        binds.append(_fmt(v))
                    else:
                        binds.append("%s:%s:%s" % (_fmt(k), _fmt(v), m))
                return binds

            binds = _convert_list(self.volumes, [])
            binds = _convert_list(self.read_only_volumes, binds, mode="ro")
            return _convert_list(self.shared_volumes, binds, mode="shared")

        @staticmethod
        def get_reserved_port(n_tries=2):
            """
                Reserve a random available port.
                It puts the door in TIME_WAIT state so that no other process gets it when asking for a random port,
                but allows processes to bind to it, due to the SO_REUSEADDR flag.
                From https://github.com/Yelp/ephemeral-port-reserve
            """
            for i in range(n_tries):
                try:
                    with contextlib.closing(socket()) as s:
                        s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
                        s.bind(('127.0.0.1', 0))

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

    return SwanSpawner