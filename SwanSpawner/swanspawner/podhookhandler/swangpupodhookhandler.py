from kubernetes_asyncio.client.models import (
    V1Affinity,
    V1EnvVar,
    V1NodeAffinity,
    V1NodeSelector,
    V1NodeSelectorRequirement,
    V1NodeSelectorTerm,
    V1Toleration,
)

from .swaneospodhookhandler import SwanEosPodHookHandler

"""
Class handling KubeSpawner.modify_pod_hook(spawner,pod) call

Configure GPU allocation for the spawned pod.
"""


class SwanGPUPodHookHandler(SwanEosPodHookHandler):
    async def get_swan_user_pod(self):
        await super().get_swan_user_pod()

        if self._gpu_enabled():
            # Configure GPU allocation
            await self._modify_pod_for_gpu()

        return self.pod

    async def _modify_pod_for_gpu(self):
        """
        Configure a pod that requested a GPU.

        Two scenarios are possible:
        - Regular user: we need to add resource requests and limits for a
        generic GPU resource to the notebook container.
        - User who participates in a SWAN event: we need to add resource
        requests and limits for the GPU resource that has been configured for
        the event. In addition, we need to add a node affinity and a taint
        toleration to the pod to ensure that event pods (and only them) are
        scheduled on resources that have been allocated for the event (and
        therefore have been labeled and tainted to host only event pods).
        """
        spawner = self.spawner
        gpu_description = spawner.user_options[spawner.gpu]
        gpu_info = spawner.gpus.get_info(gpu_description)

        # Avoid race condition in case 2 users request a GPU at the same time.
        # Keep the lock scope minimal and avoid awaiting while holding it.
        allocated_gpu = False
        with spawner.gpus.get_lock():
            if gpu_info and gpu_info.free > 0:
                gpu_info.free -= 1
                allocated_gpu = True
                spawner.log.info(
                    f"Decreased currently free count for {gpu_description}: {gpu_info.free}/{gpu_info.count} available"
                )

        if not allocated_gpu:
            error_message = f"The selected GPU flavour ({gpu_description}) is not available. Please try again later."
            raise ValueError(error_message)

        # Add affinity to nodes that are labeled with the specific GPU
        # product name that the user requested
        gpu_product_name = gpu_info.product_name
        node_selector_req = V1NodeSelectorRequirement(
            key="nvidia.com/gpu.product", operator="In", values=[gpu_product_name]
        )
        node_selector_term = V1NodeSelectorTerm(match_expressions=[node_selector_req])
        node_selector = V1NodeSelector(node_selector_terms=[node_selector_term])
        node_affinity = V1NodeAffinity(required_during_scheduling_ignored_during_execution=node_selector)
        self.pod.spec.affinity = V1Affinity(node_affinity=node_affinity)

        # Allow scheduling on Oracle for any user requesting a GPU
        tolerations = self.pod.spec.tolerations or []
        tolerations.append(V1Toleration(key="oracle/gpu", operator="Equal", value="true", effect="NoSchedule"))
        self.pod.spec.tolerations = tolerations

        if spawner.SWAN_EVENTS_ROLE in spawner.user_roles:
            # The user is a participant of an event hosted by SWAN.
            # Their pod must be allocated on a node that has been
            # provisioned exclusively for the event

            # Add affinity to nodes that have been provisioned for the
            # event, i.e. labeled with the events role name
            node_selector_req = V1NodeSelectorRequirement(key=spawner.SWAN_EVENTS_ROLE, operator="Exists")
            node_selector_term.match_expressions.append(node_selector_req)

            # Add toleration to nodes that have been provisioned for the
            # event, i.e. tainted with the events role name
            toleration = V1Toleration(key=spawner.SWAN_EVENTS_ROLE, operator="Exists", effect="NoSchedule")
            tolerations.append(toleration)

        # The GPU flavour requested by the user is available, proceed with user pod creation
        gpu_resource_name = gpu_info.resource_name

        # Add gpu label to pod (useful for filtering).
        self.pod.metadata.labels["gpu"] = gpu_resource_name.removeprefix("nvidia.com/")

        # Add to notebook container the requests and limits for the GPU
        notebook_container = self._get_pod_container("notebook")
        resources = notebook_container.resources
        resources.requests[gpu_resource_name] = "1"
        resources.limits[gpu_resource_name] = "1"

        # Configure OpenCL to use NVIDIA backend
        notebook_container.env = self._add_or_replace_by_name(
            notebook_container.env,
            V1EnvVar(name="OCL_ICD_FILENAMES", value="libnvidia-opencl.so.1"),
        )

    def _gpu_enabled(self):
        """
        return True if the user has requested a GPU
        """
        return self.spawner.user_options[self.spawner.gpu] != "none"
