# Author: Danilo Piparo, Enric Tejedor, Diogo Castro 2015
# Copyright CERN

"""CERN Specific Spawner class"""

import re, json
import os
import time
from socket import gethostname
from traitlets import Unicode, Bool, Int

from jinja2 import Environment, FileSystemLoader

def define_SwanSpawner_from(base_class):
    """
        The Spawner need to inherit from a proper upstream Spawner (i.e Docker or Kube).
        But since our personalization, added on top of those, is exactly the same for all,
        by allowing a dynamic inheritance we can re-use the same code on all cases.
        This function returns our SwanSpawner, inheriting from a class (upstream Spawner)
        given as parameter.
    """

    class SwanSpawner(base_class):

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

        customenv_special_type = Unicode(
            default_value='customenv',
            config=True,
            help='Special type for custom environments.'
        )

        eos_special_type = Unicode(
            default_value='eos',
            config=True,
            help='Special type for repository provided by a EOS folder.'
        )

        git_special_type = Unicode(
            default_value='git',
            config=True,
            help='Special repository type for Git repositories.'
        )

        default_platform = Unicode(
            default_value='x86_64-el9-gcc13-opt',
            config=True,
            help='Default platform configuration for LCG views.'
        )

        options_form_config = Unicode(
            config=True,
            help='Path to configuration file for options_form rendering.'
        )

        lcg_view_path = Unicode(
            default_value='/cvmfs/sft.cern.ch/lcg/views',
            config=True,
            help='Path where LCG views are stored in CVMFS.'
        )

        local_home = Bool(
            default_value=False,
            config=True,
            help="If True, a physical directory on the host will be the scratch space, otherwise EOS."
        )

        eos_path_format = Unicode(
            default_value='/eos/user/{username[0]}/{username}/',
            config=True,
            help='Path format of the users home folder in EOS.'
        )

        extended_timeout = Int(
            default_value=120,
            config=True,
            help="Extended timeout for users using environment script"
        )

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.this_host = gethostname().split('.')[0]
            if not self.options_form and self.options_form_config:
                # if options_form not provided, use templated options form based on configuration file
                self.options_form = self._render_templated_options_form

        def options_from_form(self, formdata):
            source_type = formdata[self.source_type][0]
            lcg = formdata[self.lcg_rel_field][0]
            platform = formdata[self.platform_field][0]
            aux_req = formdata[self.customenv_type][0].lower().split('-')
            customenv_type, customenv_type_version = '', ''
            if len(aux_req) == 2:
                customenv_type, customenv_type_version = aux_req
            repository, repository_type = '', ''
            if source_type == self.customenv_special_type:
                lcg, platform = '', self.default_platform
                repository = formdata[self.repository][0]
                repository_type = formdata[self.repository_type][0]
                if repository.startswith("http"):
                    # Extract http/domain/user/repo_name from repository URL, getting rid of the branches, tags, etc.
                    repo_pattern = r'^(https?://[^/]+/[^/\s]+/[^/\s]+).*'
                    match = re.match(repo_pattern, repository)
                    if match:
                        repository = match.group(1)
                # If the user wants to use CERNBOX_HOME, replace it with the user's CERNBOX_HOME path
                elif repository.startswith('$CERNBOX_HOME'):
                    eos_path = self.eos_path_format.format(username=self.user.name)
                    repository = repository.replace('$CERNBOX_HOME', eos_path.rstrip('/'))

            options = {}
            options[self.source_type]           = source_type
            options[self.customenv_type]        = customenv_type
            options[self.customenv_type_version] = customenv_type_version
            options[self.repository]            = repository
            options[self.repository_type]       = repository_type
            options[self.lcg_rel_field]         = lcg
            options[self.platform_field]        = platform
            options[self.user_script_env_field] = formdata[self.user_script_env_field][0]
            options[self.spark_cluster_field]   = formdata[self.spark_cluster_field][0] if self.spark_cluster_field in formdata.keys() else 'none'
            options[self.condor_pool]           = formdata[self.condor_pool][0]
            options[self.user_n_cores]          = int(formdata[self.user_n_cores][0])
            options[self.user_memory]           = formdata[self.user_memory][0] + 'G'

            self.offload = options[self.spark_cluster_field] != 'none'
            
            return options

        def get_env(self):
            """ Set base environmental variables for swan jupyter docker image """
            env = super().get_env()

            username = self.user.name
            if self.local_home:
                homepath = "/scratch/%s" %(username)
            else:
                homepath = self.eos_path_format.format(username = username)

            if not hasattr(self, 'user_uid'):
                raise Exception('Authenticator needs to set user uid (in pre_spawn_start)')

            #FIXME remove userrid and username and just use jovyan 
            #FIXME clean JPY env variables
            if self.lcg_rel_field in self.user_options:
                # session spawned via the form
                env.update(dict(
                    SOURCE_TYPE            = self.user_options[self.source_type],
                    USER                   = username,
                    NB_USER                = username,
                    USER_ID                = self.user_uid,
                    NB_UID                 = self.user_uid,
                    HOME                   = homepath,
                    EOS_PATH_FORMAT        = self.eos_path_format,
                    SERVER_HOSTNAME        = os.uname().nodename
                ))
            else:
                # session spawned via the API
                env.update(dict(
                    USER                   = "jovyan",
                    HOME                   = "/home/jovyan",
                    NB_USER                = 'jovyan',
                    USER_ID                = 1000,
                    NB_UID                 = 1000,
                    SERVER_HOSTNAME        = os.uname().nodename,
                ))

            # Enable configuration for CERN HTCondor pool
            if self.user_options[self.condor_pool] != 'none':
                env['CERN_HTCONDOR'] = 'true'

            # Enable configuration for LCG and custom environments
            if self.user_options[self.source_type] == self.customenv_special_type:
                env['AUTOENV'] = "true"
            else:
                env['ROOT_LCG_VIEW_NAME']     = self.user_options[self.lcg_rel_field]
                env['ROOT_LCG_VIEW_PLATFORM'] = self.user_options[self.platform_field]
                env['USER_ENV_SCRIPT']        = self.user_options[self.user_script_env_field]
                env['ROOT_LCG_VIEW_PATH']     = self.lcg_view_path

            return env

        async def stop(self, now=False):
            """ Overwrite default spawner to report stop of the container """

            if self._spawn_future and not self._spawn_future.done():
                # Return 124 (timeout) exit code as container got stopped by jupyterhub before successful spawn
                container_exit_code = "124"
            else:
                # Return 0 exit code as container got stopped after spawning correctly
                container_exit_code = "0"

            stop_result = await super().stop(now)

            self.log_metric(
                self.user.name,
                self.this_host,
                ".".join(["exit_container_code"]),
                container_exit_code
            )

            return stop_result

        async def poll(self):
            """ Overwrite default poll to get status of container """
            container_exit_code = await super().poll()

            # None if single - user process is running.
            # Integer exit code status, if it is not running and not stopped by JupyterHub.
            if container_exit_code is not None:
                exit_return_code = str(container_exit_code)
                if exit_return_code.isdigit():
                    value_cleaned = exit_return_code
                else:
                    result = re.search('ExitCode=(\d+)', exit_return_code)
                    if not result:
                        raise Exception("unknown exit code format for this Spawner")
                    value_cleaned = result.group(1)

                self.log_metric(
                    self.user.name,
                    self.this_host,
                    ".".join(["exit_container_code"]),
                    value_cleaned
                )

            return container_exit_code

        async def start(self):
            """
            Start the container
            """

            start_time_start_container = time.time()
            
            #if the user script exists, we allow extended timeout
            if self.user_options[self.user_script_env_field].strip()!='':
                self.start_timeout = self.extended_timeout

            # start configured container
            startup = await super().start()

            self.log_metric(
                self.user.name,
                self.this_host,
                ".".join(["start_container_duration_sec"]),
                time.time() - start_time_start_container
            )

            return startup

        def log_metric(self, user, host, metric, value):
            """ Function allowing for logging formatted metrics """
            self.log.info("user: %s, host: %s, metric: %s, value: %s" % (user, host, metric, value))

        def _render_templated_options_form(self, spawner):
            """
            Render a form from a template based on options_form_config json config file
            """
            templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
            env = Environment(loader=FileSystemLoader(templates_dir))
            template = env.get_template('options_form_template.html')

            try:
                with open(self.options_form_config) as json_file:
                    options_form_config = json.load(json_file)

                return template.render(options_form_config=options_form_config)
            except Exception as ex:
                self.log.error("Could not initialize form: %s", ex, exc_info=True)
                raise RuntimeError(
                    """
                    Could not initialize form, invalid format
                    """)

    return SwanSpawner
