###
# MPI Spawner
###
from kubernetes import client, config
from kubernetes.client.models import (V1Volume, V1VolumeMount)
from kubernetes.client.rest import ApiException
from kubespawner.utils import get_k8s_model
# import conu
# from conu.apidefs.container import Container
# from conu.backend.k8s.backend import K8sBackend
# from .k8s.client import get_core_api, get_apps_api
# from conu.apidefs.image import Image
# from conu import version
# from conu.utils.probes import Probe
# from conu.exceptions import ConuException
# from conu.utils import get_oc_api_token


# config.load_incluster_config()
#
# v1 = client.CoreV1Api()
#
# # obtain API key from OpenShift cluster. If you are not using OpenShift cluster for kubernetes tests
# # you need to replace `get_oc_api_token()` with your Bearer token. More information here:
# # https://kubernetes.io/docs/reference/access-authn-authz/authentication/
# api_key = get_oc_api_token()
#
# API_KEY = api_key
# core_api = get_core_api()
# apps_api = get_apps_api()


# def create_mynamespace(name):
#     """
#     Create namespace with name
#     :return: name of new created namespace
#     """
#
#     namespace = client.V1Namespace(metadata=client.V1ObjectMeta(name=name))
#
#     core_api.create_namespace(namespace)
#
#     # logger.info("Creating namespace: %s", name)
#
#     # save all namespaces created with this backend
#     # K8sBackend. .managed_namespaces.append(name)
#
#     # wait for namespace to be ready
#     # Probe(timeout=30, pause=5, expected_retval=True,
#     #       fnc=self._namespace_ready, namespace=name).run()
#
#     return name


class MPISpawner:

    def __init__(self, spawner, pod):
        """
        :type spawner: swanspawner.SwanKubeSpawner
        :type pod: client.V1Pod
        """
        print(" ".join(["config_dir JeodppSpawner HERE", spawner.config_dir]))

        self.spawner = spawner
        self.pod = pod
        # self.projectdir = self.spawner.config_dir + '/' + self.spawner.presetid
        # self.spawner.namespace = spawner.presetid
       # c.JeodppSpawner.namespace = NAMESPACE
        self.projectdir = spawner.stage_dir + '/' + spawner.presetid
        spawner.log.info(" ".join(["projectdir HERE", self.projectdir]))
        self.kubeinit = '/etc/project_config/kubectl_init.sh'
        spawner.log.info(" ".join(["kubeinit HERE", self.kubeinit]))

    def get_swan_user_pod(self):

        # pod labels
        pod_labels = dict(
            # lcg_release=self.spawner.user_options[self.spawner.lcg_rel_field].split('/')[0],
            # swan_user=self.spawner.user.name
            lcg_release=self.spawner.user_options[self.spawner.lcg_rel_field].split('/')[0],
            swan_user=self.spawner.user.name
        )

        # update pod labels
        self.pod.metadata.labels.update(
            pod_labels
        )

        self._init_mpi(pod_labels)

        # init user containers (notebook and side-container)
        self._init_user_containers()

        return self.pod

    def _init_user_containers(self):
        """
        Define cern related secrets for spark and eos
        """
        notebook_container = self._get_pod_container('notebook')

        username = self.spawner.user.name

        pod_spec_containers = []
        spawner_container = []
        side_container_initializer_env = []

        ## =================== uc-config-dir ===================

        self.pod.spec.volumes.append(
            get_k8s_model(
                V1Volume,
                {'name': 'uc-config-dir',
                 'hostPath': {
                     'path': self.spawner.host_config_dir + '/' + self.spawner.stage + '/' + self.spawner.presetid,
                     'type': 'DirectoryOrCreate'}
                 })
        )

        spawner_container.append(
            client.V1VolumeMount(
                name='uc-config-dir',
                mount_path='/etc/project_config'
            )
        )
        # Mount shared tokens volume that contains tokens with correct permissions
        notebook_container.volume_mounts.append(
            client.V1VolumeMount(
                name='uc-config-dir',
                mount_path='/etc/project_config'
            )
        )
        ## =================== kubectl-jeodpp-config ===================
        # mounted just in the spawner container to access all K8S cluster

        self.pod.spec.volumes.append(
            client.V1Volume(
                name='kubectl-jeodpp-config',
                secret=client.V1SecretVolumeSource(
                    secret_name='jeodpp-config',
                    default_mode=256
                )
            )
        )

        spawner_container.append(
            client.V1VolumeMount(
                name='kubectl-jeodpp-config',
                mount_path='/root/.kube/config',
                sub_path='config',
            )
        )

        ## =================== shared dir with all pods ===================

        self.pod.spec.volumes.append(
            get_k8s_model(
                V1Volume,
                {'name': 'shared-dir',
                 'hostPath': {
                     'path': self.spawner.host_shared_dir + '/' + self.spawner.stage + '/shared/' + self.spawner.presetid,
                     'type': 'DirectoryOrCreate'}
                 })
        )

        spawner_container.append(
            client.V1VolumeMount(
                name='shared-dir',
                mount_path='/home/shared'
            )
        )
        # Mount shared tokens volume that contains tokens with correct permissions
        notebook_container.volume_mounts.append(
            client.V1VolumeMount(
                name='shared-dir',
                mount_path='/home/shared'
            )
        )

        # side_container_initializer_env.append(
        #     client.V1EnvVar(
        #         name='HOSTFILE_DIR',
        #         value='/openmpi/shared/'
        #     )
        # )

        ## Test for mounting /sharedtemp
        self.pod.spec.volumes.append(
            get_k8s_model(V1Volume,
                          {'name': 'temp',
                           'hostPath': {'path': '/mnt/jeoproc/sharedscratch/' + self.spawner.presetid,
                                        'type': 'DirectoryOrCreate'}
                           })
        )
        # Note implicitly only 1 container...
        notebook_container.volume_mounts.append(
            get_k8s_model(V1VolumeMount,
                          {'name': 'temp',
                           'mountPath': '/sharedtemp'
                           })
        )

        # ================================================

        env = self.spawner.get_env()
        print("kubeinit:  " + self.kubeinit + "  and  projectdir:  " + self.projectdir)
        pod_spec_containers.append(
            client.V1Container(
                name='spawner',
                image='jeoreg.cidsn.jrc.it:5000/jeodpp-k8s/kubectl:1.13.1',
                # presetid is passed to the script to be used as namespace
                command=['sh', '-c', self.kubeinit + ' ' + self.spawner.namespace],
                args=[""],
                env=side_container_initializer_env,
                volume_mounts=spawner_container
            )
        )

        # self.pod.spec.volumes.append(
        #     client.V1Volume(
        #         name='kube-openmpi-ssh-key',
        #         secret=client.V1SecretVolumeSource(
        #             secret_name='ompi-ssh-key',
        #             default_mode=256
        #         )
        #     )
        # )
        # notebook_container.volume_mounts.append(
        #     client.V1VolumeMount(
        #         name='kube-openmpi-ssh-key',
        #         mount_path='/ssh-key/openmpi'
        #     )
        # )

        # # Verificare se togliere questo token @luca
        # self.pod.spec.volumes.append(
        #     client.V1Volume(
        #         name='default-token-xljnf',
        #         secret=client.V1SecretVolumeSource(
        #             secret_name='default-token-xljnf',
        #             default_mode=420
        #         )
        #     )
        # )
        # notebook_container.volume_mounts.append(
        #     client.V1VolumeMount(
        #         name='default-token-xljnf',
        #         mount_path='/var/run/secrets/kubernetes.io/serviceaccount'
        #     )
        # )

        # add the base containers after side container (to start after side container)
        existing_containers = self.pod.spec.containers
        pod_spec_containers.extend(existing_containers)

        # assigning pod spec containers
        self.pod.spec.containers = pod_spec_containers

    def _init_mpi(self, pod_labels):
        """
        Set cern related configuration for spark cluster and open ports
        """
        notebook_container = self._get_pod_container('notebook')
        username = self.spawner.user.name

        # configure ssh ports
        try:
            # Add SSH port for MPI Master
            notebook_container.ports = self._add_or_replace_by_name(
                notebook_container.ports,
                client.V1ContainerPort(
                    container_port=2022,
                    protocol='TCP',
                )
            )

        except ApiException as e:
            raise Exception("Could not create required user ports: %s\n" % e)

    def _get_pod_container(self, container_name):
        """
        :returns: required container from pod spec
        :rtype: client.V1Container
        """
        for container in self.pod.spec.containers:
            if container.name == container_name:
                return container

        return None

    def _add_or_replace_by_name(self, list, element):
        found = False
        for list_index in range(0, len(list)):
            if list[list_index].to_dict().get("name") == element.to_dict().get("name"):
                list[list_index] = element
                found = True
                break

        if not found:
            list.append(element)

        return list
