# Author: Danilo Piparo, Enric Tejedor 2015
# Copyright CERN

"""CERN Specific Spawner class"""

import os
import subprocess
from pprint import pformat
from dockerspawner import SystemUserSpawner
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
    AF_INET,
    SOCK_STREAM,
    gethostname,
    error as SocketError
)
import pickle, struct
import calendar, datetime


class CERNSpawner(SystemUserSpawner):

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

    session_num_ports = Int(
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

    extra_libs = Unicode(
        default_value='',
        config=True,
        help='Script to authenticate.'
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


    def __init__(self, **kwargs):
        super(CERNSpawner, self).__init__(**kwargs)
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

        env = super(CERNSpawner, self).get_env()

        username = self.user.name
        if self.local_home:
            homepath = "/scratch/%s" %(username)
        else:
            homepath = "%s/%s/%s" %(self.eos_path_prefix, username[0], username)

        env.update(dict(
            ROOT_LCG_VIEW_NAME     = self.user_options[self.lcg_rel_field],
            ROOT_LCG_VIEW_PLATFORM = self.user_options[self.platform_field],
            USER_ENV_SCRIPT        = self.user_options[self.user_script_env_field],
            ROOT_LCG_VIEW_PATH     = self.lcg_view_path,
            SPARK_CONFIG_SCRIPT    = self.spark_config_script,
            HOME                   = homepath,

            JPY_USER               = self.user.name,
            JPY_COOKIE_NAME        = self.user.server.cookie_name,
            JPY_BASE_URL           = self.user.base_url,
            JPY_HUB_PREFIX         = self.hub.base_url,
            JPY_HUB_API_URL        = self.hub.api_url,
            EXTRA_LIBS             = self.extra_libs
        ))

        # Clear old state
        self.extra_host_config['port_bindings'] = {}
        self.extra_create_kwargs['ports'] = []

        # Avoid overriding the default container output port, defined by the Spawner
        if not self.use_internal_ip:
            self.extra_host_config['port_bindings'][self.port] = (self.host_ip,)

        if self.offload:
            env['SPARK_CLUSTER_NAME'] 		    = self.user_options[self.spark_cluster_field]
            env['SERVER_HOSTNAME']   	 	    = os.uname().nodename
            env['MAX_MEMORY']         	   	    = self.user_options[self.user_memory]
            env['KRB5CCNAME']         		    =  '/tmp/krb5cc_' + self.user.name
            env['HADOOP_TOKEN_FILE_LOCATION']       =  '/spark/hadoop.toks'

            # Asks the OS for random ports to give them to Docker,
            # so that Spark can be exposed to the outside
            # Reserves the ports so that other processes don't use them
            # before Docker opens them
            for i in range(1, self.session_num_ports + 1):
                reserved_port =  self.get_reserved_port()
                env["SPARK_PORT_{port_idx}".format(port_idx=i)] = reserved_port
                self.extra_host_config['port_bindings'][reserved_port] = reserved_port
                self.extra_create_kwargs['ports'].append(reserved_port)

        return env

    @gen.coroutine
    def poll(self):
        """Check for my id in `docker ps`"""
        container = yield self.get_container()
        if not container:
            self.log.warn("container not found")
            return 0
        container_state = container['State']
        self.log.debug(
            "Container %s status: %s",
            self.container_id[:7],
            pformat(container_state),
        )

        if container_state["Running"]:
            return None
        else:
            if 'exited' == container_state['Status']:
                id = container['Id']
                self.client.remove_container(id)
                msg = '<b>We encountered an error while creating your session. Please make sure you own a CERNBox. In case you don\'t have one, it will be created automatically for you upon visiting <a target="_blank" href="https://cernbox.cern.ch">this page</a>.</b>'
                # This is a workaround to display in the spawner form page a more expressive message,
                # for example hiding the "Internal server error" string which gets automatically added.
                raise ValueError(msg)
                #return (msg)
            return (
                "ExitCode={ExitCode}, "
                "Error='{Error}', "
                "FinishedAt={FinishedAt}".format(**container_state)
                )

    def start(self, image=None):
        """Start the container and perform the operations necessary for mounting
        EOS.
        """

        username = self.user.name

        if not self.local_home: 
            # When using CERNBox as home, obtain credentials for the user
            subprocess.call(['sudo', self.auth_script, username])
            self.log.debug("We are in CERNSpawner. Credentials for %s were requested.", username)

        # If the user selects a Spark Cluster we need to generate a token to allow him in
        if self.offload:
            subprocess.call(['sudo', self.hadoop_auth_script , self.lcg_view_path + '/' + 
                self.user_options[self.lcg_rel_field] + '/' + self.user_options[self.platform_field], 
                self.user_options[self.spark_cluster_field], username])
            
	    # read the webhdfs token into env variable
            try:
                with open('/spark/'+username+'/webhdfs.toks', 'r') as myfile:
                    webhdfs_token=myfile.read()
                self.env['WEBHDFS_TOKEN'] = webhdfs_token
            except IOError:
                self.log.warn("Could not read webhdfs token file")

        # Due to dockerpy limitations in the current version, we cannot use --cpu to limit cpu.
        # This is an alternative (and old) way of doing it
        extra_host_config = {
            'cpu_period' : 100000,
            'cpu_quota' : 100000 * self.user_options[self.user_n_cores],
            'mem_limit' : self.user_options[self.user_memory]
        }

        # Temporary fix to have both slc6 and cc7 image available. It should be removed
        # as soon as we move to cc7 completely.
        if "centos7" in self.user_options[self.platform_field]:
            image = "gitlab-registry.cern.ch/swan/docker-images/systemuser:v4.0"

        self.send_metrics()

        return super(CERNSpawner, self).start(
            image=image,
            extra_host_config=extra_host_config
        )

    def send_metrics(self):
        """
        Send user chosen options to the metrics server.
        This will allow us to see what users are choosing from within Grafana.
        """

        metric_path = ".".join([self.graphite_metric_path, self.this_host, self.graphite_base_path])

        d = datetime.datetime.utcnow()
        date = calendar.timegm(d.timetuple())

        metrics = []
        for (key, value) in self.user_options.items():
            if key == self.user_script_env_field:
                path = ".".join([metric_path, key])
                metrics.append((path, (date, 1 if value else 0)))
            else:
                value_cleaned = str(value).replace('/', '_')
                path = ".".join([metric_path, key, value_cleaned])
                # Metrics values are a number
                metrics.append((path, (date, 1)))

        # Serialize the message and send everything in on single package
        payload = pickle.dumps(metrics, protocol=2)
        header = struct.pack("!L", len(payload))
        message = header + payload

        # Send the message
        conn = socket(AF_INET, SOCK_STREAM)
        conn.settimeout(2)
        conn.connect((self.graphite_server, self.graphite_server_port_batch))
        conn.send(message)
        conn.close()

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
    def get_reserved_port():
        """
            Reserve a random available port.
            It puts the door in TIME_WAIT state so that no other process gets it when asking for a random port,
            but allows processes to bind to it, due to the SO_REUSEADDR flag.
            From https://github.com/Yelp/ephemeral-port-reserve
        """
        with contextlib.closing(socket()) as s:
            s.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
            try:
                s.bind(('127.0.0.1', 0))
            except SocketError as e:
                # socket.error: [Errno 98] Address already in use
                if e.errno == 98 and port != 0:
                    s.bind((ip, 0))
                else:
                    raise

            # the connect below deadlocks on kernel >= 4.4.0 unless this arg is greater than zero
            s.listen(1)

            sockname = s.getsockname()

            # these three are necessary just to get the port into a TIME_WAIT state
            with contextlib.closing(socket()) as s2:
                s2.connect(sockname)
                s.accept()
                return sockname[1]
