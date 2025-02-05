from dataclasses import dataclass
import logging
import re
from threading import Lock, Thread
from time import sleep
from typing import Union

from kubernetes import client, config
from kubernetes.client.models import V1NodeStatus
from kubernetes.client.rest import ApiException

@dataclass
class _GPUInfo:
    '''
    Class to store information about a GPU flavour:
    - Name of the resource in k8s (e.g. nvidia.com/gpu)
    - Name of the product in k8s (e.g. NVIDIA-A100-PCIE-40GB)
    - Number of current instances of the flavour
    '''
    resource_name: str
    product_name: str
    count: int = 0

class AvailableGPUs:
    '''
    Class that spawns a thread that updates the information about
    available GPU flavours in the k8s cluster at regular intervals.
    A GPU flavour can correspond to a GPU model (e.g. "Tesla T4") or to
    a partition of a GPU card (e.g. "A100 fragment (5 GB)" ).
    '''
    UPDATE_INTERVAL = 60 * 10  # 10 minutes

    def __init__(self, events_role: str):
        self._events_role = events_role
        config.load_incluster_config()
        self._api = client.CoreV1Api()
        self._gpus = {}
        self._cordoned_gpu_nodes = []
        self._configure_logger()
        self._thread = Thread(target=self._update_gpu_info, daemon=True)
        self._thread.start()
        self._lock = Lock()

    def get_info(self, description: str) -> Union[_GPUInfo, None]:
        return self._gpus.get(description, None)

    def get_gpu_flavours(self) -> dict:
        '''
        Returns information about available GPU flavours.
        '''
        return self._gpus

    def get_cordoned_gpu_nodes(self) -> list:
        '''
        Returns a list of GPU nodes currently cordoned.
        '''
        return self._cordoned_gpu_nodes

    def get_lock(self) -> Lock:
        '''
        Returns a lock to protect the access to the information provided by
        this class.
        '''
        return self._lock

    def _configure_logger(self):
        '''
        Configures the logger for this class.
        '''
        self._logger = logging.getLogger(f'{__name__}.{__class__.__name__}')
        self._logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('[%(levelname)1.1s %(asctime)s.%(msecs).03d %(name)s %(module)s:%(lineno)d] %(message)s')
        handler.setFormatter(formatter)
        self._logger.addHandler(handler)

    def _update_gpu_info(self) -> None:
        '''
        Updates the internal information about available GPU flavours.
        '''
        while True:
            self._update_allocatable_gpu_flavours()
            sleep(self.UPDATE_INTERVAL)

    def _update_allocatable_gpu_flavours(self) -> None:
        '''
        Interrogates k8s to obtain the information about GPU flavours available
        in the cluster.
        '''
        try:
            # Filter out GPU nodes reserved for a SWAN event, if any
            gpu_nodes = self._api.list_node(label_selector = f'nvidia.com/gpu.present=true,!{self._events_role}').items
        except ApiException as e:
            self._logger.error('Error getting list of GPU nodes', e)
            return

        gpus = {}
        cordoned_gpu_nodes = []
        for node in gpu_nodes:
            if node.spec.unschedulable:
                # Node is cordoned, ignore its GPU
                cordoned_gpu_nodes.append(node.metadata.name)
                continue

            status = node.status
            labels = node.metadata.labels

            product_name = labels['nvidia.com/gpu.product']
            gpu_model = self._get_simplified_gpu_model(product_name)

            # Check MIG
            mig_config = labels['nvidia.com/mig.config']
            if mig_config == 'disabled':
                # Not partitioned, store info for full card
                self._process_full_card(gpus, gpu_model, product_name, status, labels)
            else:
                # Partitioned, store fragment info
                self._process_partitions(gpus, gpu_model, product_name, status)

        # Fully replace the stored information (in mutual exclusion)
        with self.get_lock():
            self._gpus = gpus
            self._cordoned_gpu_nodes = cordoned_gpu_nodes

        self._logger.info('Allocatable GPU flavours and their counts: ' \
                          f'{[(flavour,gpu_info.count) for flavour,gpu_info in self._gpus.items()]}')
        self._logger.info(f'Cordoned GPU nodes: {self._cordoned_gpu_nodes}')

    def _get_simplified_gpu_model(self, product_name: str) -> str:
        '''
        Returns a more readable version of the GPU model that is advertised as
        "gpu.product" in the node labels.
        '''
        if 'T4' in product_name:
            return 'Tesla T4'
        elif 'A100' in product_name:
            return 'A100'
        else:
            return product_name

    def _process_full_card(self,
                           gpus: dict,
                           gpu_model: str,
                           product_name: str,
                           node_status: V1NodeStatus,
                           node_labels: dict) -> None:
        '''
        Gets information about allocatable GPU cards
        '''
        memory = int(node_labels['nvidia.com/gpu.memory']) // 1024 # GPU RAM in GB

        # Check if the card is allocatable
        resource_name = 'nvidia.com/gpu'
        count = int(node_status.allocatable[resource_name])
        if count > 0:
            description = f'{gpu_model} ({memory} GB)'
            gpu_info = gpus.get(description, _GPUInfo(resource_name, product_name))
            gpu_info.count += count
            gpus[description] = gpu_info

    def _process_partitions(self,
                            gpus: dict,
                            gpu_model: str,
                            product_name: str,
                            node_status: V1NodeStatus) -> None:
        '''
        Gets information about allocatable GPU partitions
        '''
        # Look for MIG partitions in the allocatable resources list
        for resource_name,count in node_status.allocatable.items():
            m = re.match('nvidia.com/mig-\d+g.(\d+)gb', resource_name) # e.g. nvidia.com/mig-1g.5gb
            if m and int(count) > 0:
                memory = m.group(1)
                description = f'{gpu_model} partition ({memory} GB)'
                gpu_info = gpus.get(description, _GPUInfo(resource_name, product_name))
                gpu_info.count += int(count)
                gpus[description] = gpu_info
