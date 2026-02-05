# Author: Danilo Piparo, Enric Tejedor, Diogo Castro 2015
# Copyright CERN

"""CERN Specific Spawner class"""

import re, yaml, json
import os
import time
from socket import gethostname
from traitlets import (
    Unicode,
    Bool,
    Int,
    List
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

        gpu = 'gpu'

        use_jupyterlab_field = 'use-jupyterlab'

        spark_cluster_field = 'clusters'

        condor_pool = 'condor'

        rucio_instance = 'rucio'

        rucio_rse = 'rucioRSE'
        
        rucio_rse_mount_path = 'rse_mount_path'
        
        rucio_path_begins_at = 'path_begins_at'

        file = 'file'

        user_interface = 'user_interface'

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

        stacks_for_customenvs = List(
            default_value=[],
            config=True,
            help='List of software stacks that will use customenvs extension for building the environment'
        )

        ats_role = Unicode(
            default_value='swan-ats',
            config=True,
            help='Role to allow creation of ATS sessions.'
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
            # Dictionary with dynamic information to insert in the options form
            self._dynamic_form_info = {}

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
            # Skip validation for certain nested configuration attributes and metadata fields          
            for attr, available_options in selection.items():
                # Skip attributes that are not actual form selections
                if attr == self.rucio_instance:
                    self._validate_rucio_options(selection, options)
                elif attr in [self.rucio_rse, self.rucio_rse_mount_path, self.rucio_path_begins_at]:
                    continue
                # Only validate if available_options is a list of options
                elif type(available_options) == list and options.get(attr) not in (_.get('value') for _ in available_options):
                    self._popup_error(options, attr)

        def _validate_rucio_options(self, selection: dict, formdata: dict) -> dict:
            """
            Validate and extract Rucio-related options from the form data.
            Returns a dictionary with validated Rucio options.
            """
            rucio_options = {}
            
            # Get Rucio instance selection
            rucio_instance = formdata.get(self.rucio_instance, ['none'])
            self.log.error(f'Validating Rucio instance selection: {rucio_instance}')
            rucio_options[self.rucio_instance] = rucio_instance
            
            # If no Rucio instance selected, set defaults and return
            if rucio_instance == 'none':
                rucio_options[self.rucio_rse] = 'none'
                rucio_options[self.rucio_rse_mount_path] = ''
                rucio_options[self.rucio_path_begins_at] = '0'
                return rucio_options
            
            # Get Rucio configuration from selection
            rucio_instances = selection.get('rucio', [])
            if not rucio_instances:
                raise ValueError('Rucio configuration not found in YAML for selected LCG stack')
            
            # Find the selected Rucio instance configuration
            selected_rucio_inst = next(
                (inst for inst in rucio_instances if inst['value'] == rucio_instance), 
                None
            )
            
            if not selected_rucio_inst:
                raise ValueError(f'Invalid Rucio instance: {rucio_instance}')
            
            # Validate RSE selection
            selected_rse = formdata.get(self.rucio_rse, ['none'])
            rse_options = selected_rucio_inst.get('rse_options', [])
            
            # Validate that the selected RSE is in the available options
            valid_rses = [rse['value'] for rse in rse_options]
            if selected_rse not in valid_rses:
                raise ValueError(
                    f'Invalid RSE selection: {selected_rse} for Rucio instance: {rucio_instance}. '
                    f'Valid options are: {", ".join(valid_rses)}'
                )
            
            # Find the selected RSE configuration to get mount path and path_begins_at
            selected_rse_config = next(
                (rse for rse in rse_options if rse['value'] == selected_rse),
                None
            )
            
            if not selected_rse_config:
                raise ValueError(f'RSE configuration not found for: {selected_rse}')
            
            # Extract RSE-specific attributes
            rucio_options[self.rucio_rse] = selected_rse
            rucio_options[self.rucio_rse_mount_path] = selected_rse_config.get('rse_mount_path', '')
            rucio_options[self.rucio_path_begins_at] = str(selected_rse_config.get('path_begins_at', 0))
            
            # Validate that we received the expected hidden field values (as a sanity check)
            form_mount_path = formdata.get(self.rucio_rse_mount_path, [''])
            form_path_begins = formdata.get(self.rucio_path_begins_at, ['0'])
            
            if form_mount_path and form_mount_path != rucio_options[self.rucio_rse_mount_path]:
                self.log.warning(
                    f'Mount path mismatch: form={form_mount_path}, '
                    f'expected={rucio_options[self.rucio_rse_mount_path]}'
                )
            
            if form_path_begins and form_path_begins != rucio_options[self.rucio_path_begins_at]:
                self.log.warning(
                    f'Path begins at mismatch: form={form_path_begins}, '
                    f'expected={rucio_options[self.rucio_path_begins_at]}'
                )
            
            return rucio_options

        def _get_repo_name(self) -> str:
            """
            Extract repository name from the full repository URL.
            """
            # Variable responsible for setting the code working directory on vscode web instance (relative to the user's home directory)
            code_working_dir = ''
            if self.repository in self.user_options:
                repo_name = self.user_options[self.repository].removesuffix('/').removesuffix('.git').split('/')[-1]
                code_working_dir = os.path.join("SWAN_projects", repo_name)
            return code_working_dir

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
            options[self.gpu]                       = formdata.get(self.gpu, ['none'])[0]
            options[self.rucio_instance]            = formdata.get(self.rucio_instance, ['none'])[0]
            options[self.rucio_rse]                 = formdata.get(self.rucio_rse, ['none'])[0]
            options[self.rucio_rse_mount_path]      = formdata.get(self.rucio_rse_mount_path, [''])[0]
            options[self.rucio_path_begins_at]      = formdata.get(self.rucio_path_begins_at, ['0'])[0]

            # File to be opened when the session gets started
            options[self.file]                      = formdata.get(self.file, [''])[0]

            if options[self.software_source] == self.customenv_special_type:
                # Builders can have a version or not. When they do, we receive the following text from the form: builder:builder_version
                options[self.builder] = formdata.get(self.builder, [''])[0].lower()
                selection = self._get_selection(options_form_config, options, self.builder)

                # Validate user selected options with what is on the yaml form
                self._validate_selection_options(selection, options)

                if options[self.builder].count(':') == 1:
                    options[self.builder], options[self.builder_version] = options[self.builder].split(':')

                options[self.repository] = formdata.get(self.repository, [''])[0]
                if not options[self.repository] and options[self.builder] not in self.stacks_for_customenvs:
                    raise ValueError('Cannot create custom software environment: no repository specified')
            elif options[self.software_source] == self.lcg_special_type:
                options[self.lcg_rel_field]             = formdata[self.lcg_rel_field][0]
                options[self.platform_field]            = formdata[self.platform_field][0]
                options[self.user_script_env_field]     = formdata[self.user_script_env_field][0]
                options[self.condor_pool]               = formdata[self.condor_pool][0]
                options[self.use_local_packages_field]  = formdata.get(self.use_local_packages_field, 'unchecked')[0]

                selection = self._get_selection(options_form_config, options, self.lcg_rel_field)

                # Validate user selected options with what is on the yaml form
                self._validate_selection_options(selection, options)
                # There are software stacks that use customenvs' logic for building environments. So, we need to
                # adjust the software_source accordingly
                # Also, let the extension know which user interface to use (jupyterlab or classic notebook)
                if options[self.lcg_rel_field].split("-")[0] in self.stacks_for_customenvs:
                    options[self.software_source] = self.customenv_special_type
                    options[self.user_interface] = 'lab' if options[self.use_jupyterlab_field] == 'checked' else 'projects'
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
                CODE_WORKING_DIRECTORY = os.path.join(homepath, self._get_repo_name()),
                STACKS_FOR_CUSTOMENVS  = " ".join(self.stacks_for_customenvs),
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

                # Enable Rucio extension
                if self.user_options.get(self.rucio_instance, 'none') != 'none':
                    env.update(dict(
                        SWAN_USE_RUCIO = 'true',
                        SWAN_RUCIO_INSTANCE = self.user_options[self.rucio_instance],
                        SWAN_RUCIO_RSE = self.user_options[self.rucio_rse],
                        SWAN_RUCIO_RSE_PATH = self.user_options[self.rucio_rse_mount_path],
                        SWAN_RUCIO_RSE_PATH_BEGINS_AT = self.user_options[self.rucio_path_begins_at]
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
                "exit_container_code",
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
                    result = re.search(r'ExitCode=(\d+)', exit_return_code)
                    if not result:
                        raise Exception("unknown exit code format for this Spawner")
                    value_cleaned = result.group(1)

                self.log_metric(
                    self.user.name,
                    self.this_host,
                    "exit_container_code",
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
                "start_container_duration_sec",
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
                return template.render(options_form_config=options_form_config, dynamic_form_info=json.dumps(self._dynamic_form_info), general_domain_name=self.general_domain_name, ats_domain_name=self.ats_domain_name)
            except Exception as ex:
                self.log.error("Could not initialize form: %s", ex, exc_info=True)
                raise RuntimeError(
                    """
                    Could not initialize form, invalid format
                    """)

    return SwanSpawner