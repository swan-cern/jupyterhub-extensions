from .swanspawner import define_SwanSpawner_from
from kubespawner import KubeSpawner

from math import ceil
from traitlets import Float


class SwanKubeSpawner(define_SwanSpawner_from(KubeSpawner)):

    mem_request_fraction = Float(
        default_value=0.5,
        config=True,
        help="Fraction of the memory value selected by the user that will be requested"
    )

    async def start(self):
        """Perform the operations necessary for GPU support
        """

        if self._gpu_requested():
            self._check_gpu_access()

            self.extra_resource_guarantees["nvidia.com/gpu"] = "1"
            self.extra_resource_limits["nvidia.com/gpu"] = "1"
        elif "nvidia.com/gpu" in self.extra_resource_guarantees:
            del self.extra_resource_guarantees["nvidia.com/gpu"]
            del self.extra_resource_limits["nvidia.com/gpu"]

        # Resource requests and limits for user pods

        # CPU limit is set to what the user selects in the form
        # The request (guarantee) is statically set to 1 in the chart;
        # the resulting overcommit is acceptable since users stay idle
        # most of the time
        self.cpu_limit = self.user_options[self.user_n_cores]

        # Memory limit is set to what the user selects in the form
        # The request (guarantee) is a fraction of the above
        self.mem_limit = self.user_options[self.user_memory]
        self.mem_guarantee = ceil(self.mem_limit * self.mem_request_fraction)

        try:
            # start configured container
            startup = await super().start()

            return startup
        except BaseException as e:
            self.log.error("Error while spawning the user container: %s", e, exc_info=True)
            raise e

    def get_env(self):
        """ Set base environmental variables for swan jupyter docker image """
        env = super().get_env()

        if self._gpu_requested():
            env.update(dict(
                # Configure OpenCL to use NVIDIA backend
                OCL_ICD_FILENAMES = 'libnvidia-opencl.so.1',
            ))

        return env

    def _gpu_requested(self):
        """Returns true if the user requested a GPU"""
        return "cu" in self.user_options[self.lcg_rel_field]

    def _check_gpu_access(self):
        """Checks if the user is allowed to start a session with a GPU"""
        if "swan-gpu" not in self.user_roles:
            raise ValueError(
                """Access to GPUs is not granted;
                please <a href="https://cern.service-now.com/service-portal?id=functional_element&name=swan" target="_blank">open a Support Ticket</a>"""
                )

    # The state management methods below are a temporary fix to store `user_options`
    # in the database, so that it is restored after a hub restart.
    # To be removed when updating to JupyterHub 2.1.0 or higher, which stores
    # `user_options` in the database by default:
    # https://github.com/jupyterhub/jupyterhub/pull/3773
    def get_state(self):
        """Get the current state to save in the database"""
        state = super().get_state()
        if self.user_options:
            state['user_options'] = self.user_options
        self.log.debug("State to save for {} is: {}".format(self.user.name, state))
        return state

    def load_state(self, state):
        """Load state from the database"""
        super().load_state(state)
        if 'user_options' in state:
            self.user_options = state['user_options']
        self.log.debug("State loaded for {} is {}".format(self.user.name, state))
