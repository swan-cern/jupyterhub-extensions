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
    Int
)
import threading
from cernhandlers.proj_url_checker import has_good_chars

def build_range():
    from ast import literal_eval
    rg_str = os.environ.get('SPARK_PORT_RANGE')
    if rg_str:
        return [literal_eval(rg_str)]
    else:
        return []

class CERNSpawner(SystemUserSpawner):

    # Spark port management
    lock = threading.Lock()
    user_to_range = {}
    spark_port_ranges = build_range()

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

    auth_script = Unicode(
        default_value='',
        config=True,
        help='Script to authenticate.'
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
        default_value=4,
        config=True,
        help='Number of ports opened per user session (container).'
    )


    def __init__(self, **kwargs):
        super(CERNSpawner, self).__init__(**kwargs)
        self.offload = False

    def options_from_form(self, formdata):
        options = {}
        options[self.lcg_rel_field]         = formdata[self.lcg_rel_field][0]
        options[self.platform_field]        = formdata[self.platform_field][0]
        options[self.user_script_env_field] = formdata[self.user_script_env_field][0]
        options[self.spark_cluster_field]   = self.spark_cluster_field if self.spark_cluster_field in formdata.keys() else 'none'
        
        self.offload = options[self.spark_cluster_field] != 'none'

        return options

    def _env_default(self):
        username = self.user.name
        if self.local_home:
            homepath = "/scratch/%s" %(username)
        else:
            homepath = "%s/%s/%s" %(self.eos_path_prefix, username[0], username)

        env = super(CERNSpawner, self)._env_default()
        env.update(dict(
            ROOT_LCG_VIEW_PATH  = self.lcg_view_path,
            SPARK_CONFIG_SCRIPT = self.spark_config_script,    
            HOME                = homepath
        ))

        return env

    def get_env(self):
        env = super().get_env()
        env.update(dict(
            ROOT_LCG_VIEW_NAME     = self.user_options[self.lcg_rel_field],
            ROOT_LCG_VIEW_PLATFORM = self.user_options[self.platform_field],
            USER_ENV_SCRIPT        = self.user_options[self.user_script_env_field],
        ))

        if self.offload:
            env['SPARK_CLUSTER_NAME'] = self.user_options[self.spark_cluster_field]
            env['SERVER_HOSTNAME']    = os.uname().nodename
            
            # We need to assign the port range for the new container here, since the assigned ports will be passed as env variables.
            # These variables will be used to create the SparkConf once in the container, in the Python kernel.
            self.log.debug("Configuring container for user %s, available port ranges are %s", self.user.name, CERNSpawner.spark_port_ranges)
            self.assign_port_range()
            i = 1
            for p in self.extra_create_kwargs['ports']:
                env["SPARK_PORT_{port}".format(port=i)] = p
                i += 1

        return env

    def free_port_range(self):
        with CERNSpawner.lock:
            range = CERNSpawner.user_to_range.pop(self.user.name, None)
            if range:
                CERNSpawner.spark_port_ranges.append(range)

    @gen.coroutine
    def poll(self):
        """Check for my id in `docker ps`"""
        container = yield self.get_container()
        if not container:
            self.log.warn("container not found")
            if self.offload: self.free_port_range()
            return ""
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
                if self.offload: self.free_port_range()
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

    def out_of_ports(self):
        self.log.warning('No free ports left for Spark offloading')
        raise Exception('The limit of open Spark sessions has been reached, please try again later or start a SWAN session without Spark')

    def assign_port_range(self):
        with CERNSpawner.lock:
            ranges = CERNSpawner.spark_port_ranges
            if ranges:
                rg = ranges.pop()
                start = rg[0]
                end = start + self.session_num_ports - 1
                if end < rg[1]:
                    # There are still ports in the range, reinsert in the list
                    ranges.append((end + 1, rg[1]))
                elif end > rg[1]:
                    self.out_of_ports()

                CERNSpawner.user_to_range[self.user.name] = (start, end)
                self.log.info("Container for user %s: Spark port range (%s - %s)", self.user.name, start, end)

                port_bindings = {}
                ports = []
                for p in range(start, end + 1):
                   port_bindings[p] = p
                   ports.append(p)
                # Avoid overriding dockerspawner configuration for port Jupyter server port
                if not self.use_internal_ip:
                    port_bindings[8888] = (self.container_ip,)

                # Pass configuration to dockerspawner
                self.extra_host_config['port_bindings'] = port_bindings
                self.extra_create_kwargs['ports'] = ports
            else:
                self.out_of_ports()

    @gen.coroutine
    def start(self, image=None):
        """Start the container and perform the operations necessary for mounting
        EOS.
        """

        # Check the environment script
        script_name = self.user_options[self.user_script_env_field]
        if not has_good_chars(script_name, extra_chars = '$'):
            self.log.warning('Customisation script found and it has an issue with its name: %s', script_name)
            raise Exception('The specified path for the customisation script is not valid.')

        username = self.user.name

        if not self.local_home: 
            # When using CERNBox as home, obtain credentials for the user
            subprocess.call(['sudo', self.auth_script, username])
            self.log.debug("We are in CERNSpawner. Credentials for %s were requested.", username)

        tornadoFuture = super(CERNSpawner, self).start(
            image=image
        )

        yield tornadoFuture

    @gen.coroutine
    def stop(self, now=False):
        """Stop the container

        Make sure the corresponding Spark port range is freed, if necessary
        """

        if self.offload:
            self.free_port_range()

        yield super(CERNSpawner, self).stop(
            now=now
        )

    @property
    def volume_mount_points(self):
        """
        Override the method of SystemUserSpawner to avoid to mount the home
        of the host.
        """
        return super(SystemUserSpawner, self).volume_mount_points

    @property
    def volume_binds(self):
        """
        Override the method of SystemUserSpawner to avoid to mount the home
        of the host.
        """
        return super(SystemUserSpawner, self).volume_binds
