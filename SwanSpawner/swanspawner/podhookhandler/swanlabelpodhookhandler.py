"""
Class handling KubeSpawner.modify_pod_hook(spawner,pod) call

Add basic labels to the spawned pod.
"""


class SwanLabelPodHookHandler:
    def __init__(self, spawner, pod):
        """
        :type spawner: swanspawner.swankubespawner.SwanKubeSpawner
        :type pod: V1Pod
        """
        self.spawner = spawner
        self.pod = pod

    async def get_swan_user_pod(self):
        """
        :returns: the modified pod
        :rtype: V1Pod
        """
        # pod labels
        if (
            self.spawner.user_options[self.spawner.software_source]
            == self.spawner.lcg_special_type
        ):
            pod_labels = dict(
                software_source=self.spawner.user_options[
                    self.spawner.lcg_rel_field
                ].split("/")[0]
            )
        elif (
            self.spawner.user_options[self.spawner.software_source]
            == self.spawner.customenv_special_type
        ):
            pod_labels = dict(
                software_source=f"customenv-{self.spawner.builder}_{self.spawner.builder_version}"
            )
        else:
            pod_labels = {}

        # update pod labels
        self.pod.metadata.labels.update(pod_labels)

        # Disable adding environment variables from Kubernetes services in the same namespace
        self.pod.spec.enable_service_links = False

        return self.pod

    def _get_pod_container(self, container_name):
        """
        :returns: required container from pod spec
        :rtype: V1Container
        """
        for container in self.pod.spec.containers:
            if container.name == container_name:
                return container

        return None

    def _add_or_replace_by_name(self, list, element):
        """
        Replace the named k8s object in list whose name matches element's name, or append it if not found.

        :returns: updated list
        """
        found = False
        for list_index in range(len(list)):
            if list[list_index].to_dict().get("name") == element.to_dict().get("name"):
                list[list_index] = element
                found = True
                break

        if not found:
            list.append(element)

        return list
