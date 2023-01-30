from .swanspawner import define_SwanSpawner_from
from kubespawner import KubeSpawner

from math import ceil
from tornado import gen
from traitlets import Float


class SwanKubeSpawner(define_SwanSpawner_from(KubeSpawner)):

    mem_request_fraction = Float(
        default_value=0.5,
        config=True,
        help="Fraction of the memory value selected by the user that will be requested"
    )

    @gen.coroutine
    def start(self):
        """Perform the operations necessary for GPU support
        """

        try:
            # Enabling GPU for cuda stacks
            # Options to export nvidia device can be found in https://github.com/NVIDIA/nvidia-container-runtime#nvidia_require_
            if "cu" in self.user_options[self.lcg_rel_field]:
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
            
            # start configured container
            startup = yield super().start()

            return startup
        except BaseException as e:
            self.log.error("Error while spawning the user container: %s", e, exc_info=True)
            raise e

    def get_env(self):
        """ Set base environmental variables for swan jupyter docker image """
        env = super().get_env()

        # Enabling GPU for cuda stacks
        # Options to export nvidia device can be found in https://github.com/NVIDIA/nvidia-container-runtime#nvidia_require_
        if "cu" in self.user_options[self.lcg_rel_field]:
            env.update(dict(
                NVIDIA_VISIBLE_DEVICES      = 'all',  # We are making visible all the devices, if the host has more that one can be used.
                NVIDIA_DRIVER_CAPABILITIES  = 'compute,utility',
                NVIDIA_REQUIRE_CUDA         = 'cuda>=10.0 driver>=410',
            ))

        return env

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
