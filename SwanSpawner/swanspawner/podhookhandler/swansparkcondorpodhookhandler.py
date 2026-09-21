import asyncio
from subprocess import CalledProcessError

from kubernetes_asyncio.client.models import (
    V1ContainerPort,
    V1EnvVar,
    V1ObjectMeta,
    V1Secret,
    V1SecretVolumeSource,
    V1Service,
    V1ServicePort,
    V1ServiceSpec,
    V1Volume,
    V1VolumeMount,
)
from kubernetes_asyncio.client.rest import ApiException

from .swangpupodhookhandler import SwanGPUPodHookHandler

"""
Class handling KubeSpawner.modify_pod_hook(spawner,pod) call

Setup Spark and HTCondor for the spawned pod.
"""


class SwanSparkCondorPodHookHandler(SwanGPUPodHookHandler):
    _SPARK_REQUIRED_PORTS = 18
    _CONDOR_REQUIRED_PORTS = 5

    async def get_swan_user_pod(self):
        await super().get_swan_user_pod()

        required_ports = 0

        if self._spark_enabled():
            # Configure Spark clusters at CERN
            await self._init_spark()

            cluster = self.spawner.user_options[self.spawner.spark_cluster_field]
            if cluster == "k8s":
                secret_name = await self._init_sparkk8s_config()
                # Modify user containers (notebook and side-container)
                self._modify_containers_for_spark(secret_name)

            # Add required Spark ports
            required_ports += self._SPARK_REQUIRED_PORTS

        if self._condor_enabled():
            # Configure HTCondor pool at CERN
            required_ports += self._CONDOR_REQUIRED_PORTS

        if required_ports > 0:
            await self._open_ports(required_ports)

        return self.pod

    async def _init_sparkk8s_config(self):
        """
        Create config for Spark on k8s
        """

        swan_container_namespace = self.spawner.swan_container_namespace
        username = self.spawner.user.name
        hadoop_secret_name = f"hadoop-tokens-{username}"

        try:
            # Setup the user and generate user kube config
            proc = await asyncio.create_subprocess_exec(
                "sudo",
                "--preserve-env=SWAN_DEV",
                "/srv/jupyterhub/private/sparkk8s_token.sh",
                username,
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
            if proc.returncode != 0:
                raise CalledProcessError
            k8suser_config_base64 = stdout.decode("ascii")
        except Exception:
            # if no access, all good for now
            raise ValueError("Could not setup user on k8s")

        # Create V1Secret with the k8s user config
        try:
            secret_data = V1Secret()
            secret_meta = V1ObjectMeta()
            secret_meta.name = hadoop_secret_name
            secret_meta.namespace = swan_container_namespace
            secret_data.metadata = secret_meta
            secret_data.data = {}
            secret_data.data["k8s-user.config"] = k8suser_config_base64

            try:
                await self.spawner.api.read_namespaced_secret(
                    hadoop_secret_name, swan_container_namespace
                )
                exists = True
            except ApiException:
                exists = False

            if exists:
                await self.spawner.api.replace_namespaced_secret(
                    hadoop_secret_name, swan_container_namespace, secret_data
                )
            else:
                await self.spawner.api.create_namespaced_secret(
                    swan_container_namespace, secret_data
                )
        except ApiException as e:
            raise RuntimeError("Could not create required hadoop secret") from e

        return hadoop_secret_name

    def _modify_containers_for_spark(self, hadoop_secret_name):
        """
        Configure CERN-related secrets for Spark
        """

        notebook_container = self._get_pod_container("notebook")
        side_container = self._get_pod_container("side-container")

        # pod volume to mount generated hadoop tokens and
        # side-container volume mount with generated tokens
        self.pod.spec.volumes.append(
            # V1Secret for tokens without adjusted permissions
            V1Volume(
                name=hadoop_secret_name,
                secret=V1SecretVolumeSource(
                    secret_name=hadoop_secret_name,
                ),
            )
        )
        side_container.volume_mounts.append(
            V1VolumeMount(
                name=hadoop_secret_name, mount_path="/srv/side-container/hadoop"
            )
        )

        # configuration to access Spark k8s cluster
        notebook_container.env = self._add_or_replace_by_name(
            notebook_container.env,
            V1EnvVar(name="KUBECONFIG", value="/srv/notebook/tokens/k8s-user.config"),
        )

    def _spark_enabled(self):
        """
        Helper function to determine if spark related configuration is necessary
        raise exception if user has not access to the selected spark cluster
        return True if spark cluster is selected and user has access to the selected spark cluster
        return False if spark cluster is not selected
        """

        user_roles = self.spawner.user_roles
        cluster = self.spawner.user_options.get(
            self.spawner.spark_cluster_field, "none"
        )

        if cluster == "hadoop-analytix" and "analytix" not in user_roles:
            raise ValueError(
                """
              Access to the Analytix cluster is not granted.
              Please <a href="https://cern.service-now.com/service-portal?id=sc_cat_item&name=access-cluster-hadoop&se=Hadoop-Service" target="_blank">request access</a>
              """
            )
        elif cluster == "hadoop-nxcals" and "hadoop-nxcals" not in user_roles:
            raise ValueError(
                """
              Access to the NXCALS cluster is not granted.
              Please <a href="http://nxcals-docs.web.cern.ch/current/user-guide/data-access/nxcals-access-request/" target="_blank">request access</a>
              """
            )
        elif cluster != "none":
            return True
        return False

    async def _init_spark(self):
        """
        Set CERN-related configuration for Spark clusters
        """

        notebook_container = self._get_pod_container("notebook")
        username = self.spawner.user.name

        cluster = self.spawner.user_options[self.spawner.spark_cluster_field]
        max_mem = self.spawner.user_options[self.spawner.user_memory]

        # add basic spark envs

        notebook_container.env = self._add_or_replace_by_name(
            notebook_container.env, V1EnvVar(name="SPARK_CLUSTER_NAME", value=cluster)
        )
        notebook_container.env = self._add_or_replace_by_name(
            notebook_container.env, V1EnvVar(name="SPARK_USER", value=username)
        )
        notebook_container.env = self._add_or_replace_by_name(
            notebook_container.env, V1EnvVar(name="MAX_MEMORY", value=max_mem)
        )

        # add spark auth required env
        notebook_container.env = self._add_or_replace_by_name(
            notebook_container.env,
            V1EnvVar(
                name="SPARK_AUTH_REQUIRED",
                value="true",
            ),
        )

        # add spark config env
        conf_home = self.spawner.spark_configuration_path
        if cluster == "k8s":
            spark_conf_script = f"{conf_home}/k8s-swan-setconf.sh"
        else:
            spark_conf_script = f"{conf_home}/hadoop-swan-setconf.sh"

        notebook_container.env = self._add_or_replace_by_name(
            notebook_container.env,
            V1EnvVar(name="SPARK_CONFIG_SCRIPT", value=spark_conf_script),
        )

    def _condor_enabled(self):
        """
        return True if the user has selected an HTCondor pool.
        """
        condor_pool = self.spawner.user_options.get(self.spawner.condor_pool, "none")
        return condor_pool != "none"

    async def _open_ports(self, num_ports):
        """
        Create a service that opens the necessary ports to integrate with external
        computing resources.
        """

        swan_container_namespace = self.spawner.swan_container_namespace
        computing_ports_service = f"computing-ports-{self.spawner.user.name}"
        notebook_container = self._get_pod_container("notebook")

        try:
            # Define `num_ports` random NodePorts on the cluster using V1Service
            service_template_ports = []
            for port_id in range(1, num_ports + 1):
                service_template_ports.append(
                    V1ServicePort(name=f"comp-port-{port_id}", port=port_id)
                )
            service_template = V1Service(
                api_version="v1",
                kind="Service",
                metadata=V1ObjectMeta(name=computing_ports_service),
                spec=V1ServiceSpec(
                    selector=self.pod.metadata.labels,  # attach this service to the user pod
                    ports=service_template_ports,
                    type="NodePort",
                    # To preserve the source IP of the incoming connection,
                    # so that it is possible to connect to the Spark WebUI
                    external_traffic_policy="Local",
                ),
            )

            # Create V1Service which allocates random ports
            try:
                # use existing if possible
                service = await self.spawner.api.read_namespaced_service(
                    computing_ports_service, swan_container_namespace
                )
            except ApiException:
                # not existing, create
                try:
                    service = await self.spawner.api.create_namespaced_service(
                        swan_container_namespace, service_template
                    )
                except ApiException as e:
                    raise RuntimeError(
                        "Could not create service that allocates random ports for computing integrations"
                    ) from e

            # Replace the service with allocated nodeports to map nodeport:targetport
            # and set these ports for the notebook container
            ports = []
            for port_id in range(len(service.spec.ports)):
                name = service.spec.ports[port_id].name
                node_port = service.spec.ports[port_id].node_port
                service.spec.ports[port_id] = V1ServicePort(
                    name=name,
                    node_port=node_port,
                    port=node_port,
                    target_port=node_port,
                )

                # Open proper ports in the notebook container to map nodeport:targetport
                notebook_container.ports = self._add_or_replace_by_name(
                    notebook_container.ports,
                    V1ContainerPort(
                        name=name,
                        container_port=node_port,
                        # this is needed - hadoop-yarn webapp crashes on ApplicationProxy UI
                        host_port=node_port,
                    ),
                )

                ports.append(str(node_port))

            await self.spawner.api.replace_namespaced_service(
                computing_ports_service, swan_container_namespace, service
            )

            # Add ports env for computing integrations
            notebook_container.env = self._add_or_replace_by_name(
                notebook_container.env,
                V1EnvVar(name="COMPUTING_PORTS", value=",".join(ports)),
            )
        except ApiException as e:
            raise RuntimeError("Could not create required user ports") from e
