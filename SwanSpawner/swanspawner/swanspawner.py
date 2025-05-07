# Author: Danilo Piparo, Enric Tejedor, Diogo Castro 2015
# Copyright CERN

"""CERN Specific Spawner class"""

import re, yaml
import os
import time
from socket import gethostname
from traitlets import (
    Unicode,
    Bool,
    Int
)

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

        software_source = 'software_source'

        builder = 'builder'

        builder_version = 'builder_version'

        repository = 'repository'

        lcg_rel_field = 'lcg'

        use_local_packages_field = 'use-local-packages'

        platform_field = 'platforms'

        user_script_env_field = 'scriptenv'

        user_n_cores = 'cores'

        user_memory = 'memory'

        use_jupyterlab_field = 'use-jupyterlab'

        spark_cluster_field = 'clusters'

        condor_pool = 'condor'

        file = 'file'

        customenv_special_type = 'customenv'

        lcg_special_type = 'lcg'

        eos_special_type = 'eos'

        options_form_config = Unicode(
            config=True,
            help='Path to configuration file for options_form rendering.'
        )

        general_domain_name = Unicode(
            default_value='swan.cern.ch',
            config=True,
            help='Domain name of the general SwanHub instance.'
        )

        ats_domain_name = Unicode(
            default_value='ats.swan.cern.ch',
            config=True,
            help='Domain name of the ATS SwanHub instance.'
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

        def _popup_error(self, options: dict, invalid_selection: str) -> None:
            """ Raise an error if the selection is invalid """
            err_msg = f'Invalid {invalid_selection} selection: {options[invalid_selection]}'
            self.log.error(err_msg)
            raise ValueError(err_msg)

        def _get_selection(self, options_form_config: dict, options: dict, parent: str) -> dict:
            """ 
            Get major selection which can be either a builder, for customenvs, or a LCG release.
            Each selection has its own minor options that need to be validated, as well.
            """
            selection = next((_ for _ in options_form_config[f'{options[self.software_source]}_options'] if _['type'] == 'selection' and options[parent] == _[parent]['value']), None)
            if not selection:
                self._popup_error(options, parent)
            return selection

        def _validate_selection_options(self, selection: dict, options: dict) -> None:
            """
            Ensure the validity of the minor options selected by the user,
            to prevent the acceptance of malicious / erroneous values
            """
            for attr, available_options in selection.items():
                if type(available_options) == list and options.get(attr) not in (_.get('value') for _ in available_options):
                    self._popup_error(options, attr)

        def options_from_form(self, formdata: dict) -> dict:
            """
            Get the options from the form and validate them according to the available options
            given by the configuration file, and raises errors for invalid selections.
            """
            with open(self.options_form_config) as yaml_file:
                options_form_config = yaml.safe_load(yaml_file)

            # Get common options
            options = {}
            options[self.software_source]           = formdata[self.software_source][0]
            options[self.user_n_cores]              = formdata[self.user_n_cores][0]
            options[self.user_memory]               = formdata[self.user_memory][0]
            options[self.spark_cluster_field]       = formdata.get(self.spark_cluster_field, ['none'])[0]
            options[self.use_jupyterlab_field]      = formdata.get(self.use_jupyterlab_field, 'unchecked')[0]
            # File to be opened when the session gets started
            options[self.file]                      = formdata.get(self.file, [''])[0]

            if options[self.software_source] == self.customenv_special_type:
                options[self.repository] = formdata[self.repository][0]
                if not options[self.repository]:
                    raise ValueError('Cannot create custom software environment: no repository specified')

                # Builders can have a version or not. When they do, we receive the following text from the form: builder:builder_version
                options[self.builder] = formdata.get(self.builder, [''])[0].lower()
                selection = self._get_selection(options_form_config, options, self.builder)

                # Validate user selected options with what is on the yaml form
                self._validate_selection_options(selection, options)

                if options[self.builder].count(':') == 1:
                    options[self.builder], options[self.builder_version] = options[self.builder].split(':')
            elif options[self.software_source] == self.lcg_special_type:
                options[self.lcg_rel_field]             = formdata[self.lcg_rel_field][0]
                options[self.platform_field]            = formdata[self.platform_field][0]
                options[self.user_script_env_field]     = formdata[self.user_script_env_field][0]
                options[self.condor_pool]               = formdata[self.condor_pool][0]
                options[self.use_local_packages_field]  = formdata.get(self.use_local_packages_field, 'unchecked')[0]

                selection = self._get_selection(options_form_config, options, self.lcg_rel_field)

                # Validate user selected options with what is on the yaml form    
                self._validate_selection_options(selection, options)
            else:
                self._popup_error(options, self.software_source)

            # Format resource options to do request
            options[self.user_n_cores] = int(options[self.user_n_cores])
            options[self.user_memory]  = options[self.user_memory] + 'G'
            self.offload = options[self.spark_cluster_field] != 'none'

            return options

        def get_env(self):
            """ Set base environmental variables for swan jupyter docker image """
            env = super().get_env()

            username = self.user.name
            if self.local_home:
                homepath = "/home/%s" %(username)
            else:
                homepath = self.eos_path_format.format(username = username)

            if not hasattr(self, 'user_uid'):
                raise Exception('Authenticator needs to set user uid (in pre_spawn_start)')

            #FIXME remove userrid and username and just use jovyan 
            #FIXME clean JPY env variables
            env.update(dict(
                SOFTWARE_SOURCE        = self.user_options[self.software_source],
                USER                   = username,
                NB_USER                = username,
                USER_ID                = self.user_uid,
                NB_UID                 = self.user_uid,
                HOME                   = homepath,
                EOS_PATH_FORMAT        = self.eos_path_format,
                SERVER_HOSTNAME        = os.uname().nodename
            ))

            # Enable LCG-related variables
            if self.user_options[self.software_source] == self.lcg_special_type:
                env.update(dict(
                    ROOT_LCG_VIEW_NAME       = self.user_options[self.lcg_rel_field],
                    ROOT_LCG_VIEW_PLATFORM   = self.user_options[self.platform_field],
                    USER_ENV_SCRIPT          = self.user_options[self.user_script_env_field],
                    ROOT_LCG_VIEW_PATH       = self.lcg_view_path
                ))

                # Append path of user packages installed on CERNBox to PYTHONPATH
                if self.user_options.get(self.use_local_packages_field) == 'checked':
                    env.update(dict(
                        SWAN_USE_LOCAL_PACKAGES = 'true'
                    ))

                # Enable configuration for CERN HTCondor pool
                if self.user_options.get(self.condor_pool, 'none') != 'none':
                    env.update(dict(
                        CERN_HTCONDOR = 'true'
                    ))

            # Enable JupyterLab interface
            if self.user_options[self.use_jupyterlab_field] == 'checked':
                env.update(dict(
                    SWAN_USE_JUPYTERLAB = 'true'
                ))

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

                if int(value_cleaned) == 127:
                    self.log.warning(
                        "Detected user environment script setup failure (exit code 127)")
                    raise RuntimeError(
                        f"User environment script failed: "
                        f"Could not find the script '{self.user_options[self.user_script_env_field]}'."
                    )

            return container_exit_code

        async def start(self):
            """
            Start the container
            """

            start_time_start_container = time.time()
            
            #if the user script exists, we allow extended timeout
            if self.user_options.get(self.user_script_env_field, '').strip() != '':
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
            Render a form from a template based on options_form_config yaml config file
            """
            templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
            env = Environment(loader=FileSystemLoader(templates_dir))
            template = env.get_template('options_form_template.html')

            try:
                with open(self.options_form_config) as yaml_file:
                    options_form_config = yaml.safe_load(yaml_file)

                return template.render(options_form_config=options_form_config, general_domain_name=self.general_domain_name, ats_domain_name=self.ats_domain_name)
            except Exception as ex:
                self.log.error("Could not initialize form: %s", ex, exc_info=True)
                raise RuntimeError(
                    """
                    Could not initialize form, invalid format
                    """)

    return SwanSpawner