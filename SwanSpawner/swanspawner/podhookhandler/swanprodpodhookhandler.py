import asyncio
from subprocess import CalledProcessError

import escapism
from kubernetes_asyncio.client.models import (
    V1ConfigMapVolumeSource,
    V1Container,
    V1EmptyDirVolumeSource,
    V1EnvVar,
    V1EnvVarSource,
    V1KeyToPath,
    V1ObjectFieldSelector,
    V1ObjectMeta,
    V1Secret,
    V1SecretVolumeSource,
    V1SecurityContext,
    V1Volume,
    V1VolumeMount,
)
from kubernetes_asyncio.client.rest import ApiException

from .swanpodhookhandler import SwanPodHookHandler

"""
Class handling KubeSpawner.modify_pod_hook(spawner,pod) call
"""


class SwanProdPodHookHandler(SwanPodHookHandler):
    async def get_swan_user_pod(self):
        super().get_swan_user_pod()

        # Check if the user has access to the Technical Network
        self._check_tn_access()

        # When eos is enabled, create eos token and side-container for token refresh
        # Note: Spark also requires the side container so Spark is disabled when EOS is disabled.
        if self.spawner.eos_enabled:
            eos_secret_name = await self._init_eos_secret()
            self._init_eos_containers(eos_secret_name)

        return self.pod

    def _check_tn_access(self):
        """
        Helper function to check if this SWAN deployment is exposed to the Technical Network
        and, if so, validate if the user has access to it.
        """
        user_roles = self.spawner.user_roles
        ats_role = self.spawner.ats_role
        tn_enabled = self.spawner.tn_enabled

        if tn_enabled and ats_role not in user_roles:
            raise ValueError("Access to the Technical Network is not granted.")

    async def _init_eos_secret(self):
        # Get configuration parameters from environment variables
        swan_container_namespace = self.spawner.swan_container_namespace

        username = escapism.escape(
            self.spawner.user.name, safe=self.spawner.safe_chars, escape_char="-"
        ).lower()
        eos_secret_name = "eos-tokens-%s" % username

        try:
            # Retrieve eos token for user
            proc = await asyncio.create_subprocess_exec(
                "sudo",
                "--preserve-env=SWAN_DEV",
                "/srv/jupyterhub/private/eos_token.sh",
                username,
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)
            if proc.returncode != 0:
                raise CalledProcessError
            eos_token_base64 = stdout.decode("ascii")
        except Exception:
            raise ValueError("Could not create required user credential")

        # ITHADOOP-819 - Ports need to be opened using service creation, and later assigning allocated service nodeport to a pod
        # Create V1Secret with eos token
        secret_data = V1Secret()

        secret_meta = V1ObjectMeta()
        secret_meta.name = eos_secret_name
        secret_meta.namespace = swan_container_namespace
        secret_meta.labels = {"swan_user": username}
        secret_data.metadata = secret_meta
        secret_data.data = {}
        secret_data.data["krb5cc"] = eos_token_base64

        try:
            # eos-tokens secret is cleaned when user session ends, so try creating it
            await self.spawner.api.create_namespaced_secret(
                swan_container_namespace, secret_data
            )
        except ApiException:
            # A secret with the same name exists, probably a remnant of a wrongly-terminated session, then replace it
            try:
                await self.spawner.api.replace_namespaced_secret(
                    eos_secret_name, swan_container_namespace, secret_data
                )
            except ApiException as e:
                raise Exception("Could not create required eos secret: %s\n" % e)

        return eos_secret_name

    def _init_eos_containers(self, eos_secret_name):
        """
        Define cern related secrets for spark and eos
        """
        notebook_container = self._get_pod_container("notebook")
        username = self.spawner.user.name

        pod_spec_containers = []
        side_container_volume_mounts = []

        # Shared directory between notebook and side-container for tokens with correct privileges
        self.pod.spec.volumes.append(
            V1Volume(
                name="shared-pod-volume",
                empty_dir=V1EmptyDirVolumeSource(medium="Memory"),
            )
        )
        side_container_volume_mounts.append(
            V1VolumeMount(name="shared-pod-volume", mount_path="/srv/notebook")
        )

        # Mount shared tokens volume that contains tokens with correct permissions
        notebook_container.volume_mounts.append(
            V1VolumeMount(name="shared-pod-volume", mount_path="/srv/notebook")
        )

        # pod volume to mount generated eos tokens and
        # side-container volume mount with generated tokens
        self.pod.spec.volumes.append(
            V1Volume(
                name=eos_secret_name,
                secret=V1SecretVolumeSource(
                    secret_name="eos-tokens-%s" % username,
                ),
            )
        )
        side_container_volume_mounts.append(
            V1VolumeMount(name=eos_secret_name, mount_path="/srv/side-container/eos")
        )

        # define eos kerberos credentials path for Jupyter server in notebook container
        notebook_container.env = self._add_or_replace_by_name(
            notebook_container.env,
            V1EnvVar(name="KRB5CCNAME", value="/srv/notebook/tokens/krb5cc"),
        )

        # define eos kerberos credentials path for notebook and terminal processes in notebook container
        notebook_container.env = self._add_or_replace_by_name(
            notebook_container.env,
            V1EnvVar(
                name="KRB5CCNAME_NB_TERM",
                value="/srv/notebook/tokens/writable/krb5cc_nb_term",
            ),
        )

        # Set server hostname of the pod running jupyterhub
        notebook_container.env = self._add_or_replace_by_name(
            notebook_container.env,
            V1EnvVar(
                name="SERVER_HOSTNAME",
                value_from=V1EnvVarSource(
                    field_ref=V1ObjectFieldSelector(field_path="spec.nodeName")
                ),
            ),
        )

        # append as first (it will be first to spawn) side container which currently:
        #  - refreshes the kerberos token and adjust permissions for the user
        self.pod.spec.volumes.append(
            V1Volume(
                name="side-container-scripts",
                config_map=V1ConfigMapVolumeSource(
                    name="swan-scripts-cern",
                    items=[
                        V1KeyToPath(
                            key="side_container_tokens_perm.sh",
                            path="side_container_tokens_perm.sh",
                        )
                    ],
                    default_mode=356,
                ),
            )
        )
        side_container_volume_mounts.append(
            V1VolumeMount(
                name="side-container-scripts",
                mount_path="/srv/side-container/side_container_tokens_perm.sh",
                sub_path="side_container_tokens_perm.sh",
            )
        )

        env = self.spawner.get_env()
        pod_spec_containers.append(
            V1Container(
                name="side-container",
                image=notebook_container.image,
                command=["/srv/side-container/side_container_tokens_perm.sh"],
                args=[
                    env["USER_ID"],
                    env["USER_ID"],
                    str(self.spawner.cull_period),
                ],
                volume_mounts=side_container_volume_mounts,
                security_context=V1SecurityContext(run_as_user=0),
            )
        )

        # add the base containers after side container (to start after side container)
        existing_containers = self.pod.spec.containers
        pod_spec_containers.extend(existing_containers)

        # assigning pod spec containers
        self.pod.spec.containers = pod_spec_containers
