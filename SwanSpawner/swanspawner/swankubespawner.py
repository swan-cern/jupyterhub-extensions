from .swanspawner import define_SwanSpawner_from
from kubespawner import KubeSpawner

from kubernetes_asyncio.client.rest import ApiException

import os
from math import ceil
from traitlets import Float, Unicode


class SwanKubeSpawner(define_SwanSpawner_from(KubeSpawner)):

    mem_request_fraction = Float(
        default_value=0.5,
        config=True,
        help="Fraction of the memory value selected by the user that will be requested"
    )

    centos7_image = Unicode(
        config=True,
        help='URL of the CentOS7 user image.'
    )

    async def start(self):
        """Perform extra configurations required for SWAN session spawning in
        kubernetes.
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

        # An Alma9-based user image is configured by default via the chart
        # settings, but users could still select a CentOS7 platform.
        # In that case, reconfigure to use a CentOS7-based user image
        if 'centos7' in self.user_options[self.platform_field]:
            image = self.centos7_image
            if not image:
                raise RuntimeError('The user selected the CentOS7 platform, but no CentOS7 image was configured')
            self.image = image

        try:
            # start configured container
            startup = await super().start()

            return startup
        except BaseException as e:
            self.log.error("Error while spawning the user container: %s", e, exc_info=True)
            raise e

    async def stop(self, now=False):
        '''Do custom cleanup after terminating user pod'''
        try:
            await super().stop()
        finally:
            # Delete Kubernetes secret storing EOS kerberos ticket of the user
            username = self.user.name
            eos_secret_name = f'eos-tokens-{username}'
            namespace = os.environ.get('POD_NAMESPACE', 'default')
            self.log.info(f'Deleting secret {namespace}:{eos_secret_name}')
            try:
                await self.api.delete_namespaced_secret(eos_secret_name, namespace)
            except ApiException as e:
                self.log.error('Error deleting secret {namespace}:{eos_secret_name}: {e}')

            # Spark-related cleanup
            spark_cluster = self.user_options[self.spark_cluster_field]
            if spark_cluster and spark_cluster != 'none':
                # Delete NodePort service opening ports for the user Spark processes
                spark_ports_service = f'spark-ports-{username}'
                self.log.info(f'Deleting service {namespace}:{spark_ports_service}')
                try:
                    await self.api.delete_namespaced_service(spark_ports_service, namespace)
                except ApiException as e:
                    self.log.error('Error deleting service {namespace}:{spark_ports_service}: {e}')

                # Delete Kubernetes secret with Hadoop delegation tokens
                hadoop_secret_name = f'hadoop-tokens-{username}'
                self.log.info(f'Deleting secret {namespace}:{hadoop_secret_name}')
                try:
                    await self.api.delete_namespaced_secret(hadoop_secret_name, namespace)
                except ApiException as e:
                    self.log.error('Error deleting secret {namespace}:{hadoop_secret_name}: {e}')

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
