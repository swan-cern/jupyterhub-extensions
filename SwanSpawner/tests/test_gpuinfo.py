"""
Unit tests for _gpuinfo.py
"""

from threading import Lock
from unittest.mock import Mock

from kubernetes.client.models import V1NodeStatus
from swanspawner._gpuinfo import AvailableGPUs

EVENTS_ROLE = "swan-events"
LHCB_ROLE = "swan-lhcb"


class _MockAvailableGPUs(AvailableGPUs):
    """Bypasses __init__ so tests can run without a Kubernetes cluster."""

    def __init__(
        self,
        node_to_flavor=None,
        gpus=None,
        cordoned=None,
        lhcb_nodes=None,
        events_nodes=None,
    ):
        self._events_role = EVENTS_ROLE
        self._lhcb_role = LHCB_ROLE
        self._gpus = gpus or {}
        self._node_to_flavor = node_to_flavor or {}
        self._cordoned_gpu_nodes = cordoned or []
        self._lhcb_nodes = lhcb_nodes or set()
        self._events_nodes = events_nodes or set()
        self._lock = Lock()


# ---------------------------------------------------------------------------
# TestProcessFullCard
# ---------------------------------------------------------------------------


class TestProcessFullCard:
    def _process_card(self, gpus, node_to_flavor, node, allocatable=None):
        """Run _process_full_card on a mock node with a single Tesla T4 GPU attached"""

        if allocatable is None:
            allocatable = {"nvidia.com/gpu": "1"}
        node_status = Mock(spec=V1NodeStatus, allocatable=allocatable)
        # For brevity, only the node labels actually relevant for _gpuinfo.py for non-partitionnable cards
        node_labels = {
            "nvidia.com/gpu.present": "true",
            "nvidia.com/gpu.product": "Tesla-T4",
            "nvidia.com/gpu.memory": "15360",
        }
        mock = _MockAvailableGPUs()

        mock._process_full_card(
            gpus,
            "Tesla T4",
            "NVIDIA-T4-15GB",
            node_to_flavor,
            node_status,
            node_labels,
            node,
        )

    def test_single_node(self):
        gpus, node_to_flavor = {}, {}
        self._process_card(gpus, node_to_flavor, "node-0")

        assert "Tesla T4 (15 GB)" in gpus
        assert gpus["Tesla T4 (15 GB)"].count == 1
        assert node_to_flavor == {("node-0", "nvidia.com/gpu"): "Tesla T4 (15 GB)"}

    def test_two_nodes(self):
        gpus, node_to_flavor = {}, {}
        self._process_card(gpus, node_to_flavor, "node-0")
        self._process_card(gpus, node_to_flavor, "node-1")

        assert "Tesla T4 (15 GB)" in gpus
        assert gpus["Tesla T4 (15 GB)"].count == 2
        assert node_to_flavor == {
            ("node-0", "nvidia.com/gpu"): "Tesla T4 (15 GB)",
            ("node-1", "nvidia.com/gpu"): "Tesla T4 (15 GB)",
        }

    def test_node_status_not_ready(self):
        gpus, node_to_flavor = {}, {}
        self._process_card(gpus, node_to_flavor, "node-0", allocatable={})

        assert gpus == {}
        assert node_to_flavor == {}


# ---------------------------------------------------------------------------
# TestProcessPartitions
# ---------------------------------------------------------------------------


class TestProcessPartitions:
    def _process_partitions(self, gpus, node_to_flavor, node, allocatable=None):
        """Run _process_partitions on a mock node with a single partitionnable A100 GPU attached"""

        if allocatable is None:
            allocatable = {
                "nvidia.com/gpu": "0",
                "nvidia.com/mig-1g.5gb": "0",
                "nvidia.com/mig-2g.10gb": "2",
                "nvidia.com/mig-3g.20gb": "1",
            }
        node_status = Mock(spec=V1NodeStatus, allocatable=allocatable)
        mock = _MockAvailableGPUs()

        mock._process_partitions(
            gpus,
            "A100",
            "NVIDIA-A100-40GB",
            node_to_flavor,
            node_status,
            node,
        )

    def test_single_node(self):
        gpus, node_to_flavor = {}, {}
        self._process_partitions(gpus, node_to_flavor, "node-0")

        assert "A100 partition (5 GB)" not in gpus

        assert "A100 partition (10 GB)" in gpus
        assert gpus["A100 partition (10 GB)"].count == 2

        assert "A100 partition (20 GB)" in gpus
        assert gpus["A100 partition (20 GB)"].count == 1

        assert node_to_flavor == {
            ("node-0", "nvidia.com/mig-2g.10gb"): "A100 partition (10 GB)",
            ("node-0", "nvidia.com/mig-3g.20gb"): "A100 partition (20 GB)",
        }

    def test_two_nodes(self):
        gpus, node_to_flavor = {}, {}
        self._process_partitions(gpus, node_to_flavor, "node-0")
        self._process_partitions(gpus, node_to_flavor, "node-1")

        assert "A100 partition (5 GB)" not in gpus

        assert "A100 partition (10 GB)" in gpus
        assert gpus["A100 partition (10 GB)"].count == 4

        assert "A100 partition (20 GB)" in gpus
        assert gpus["A100 partition (20 GB)"].count == 2

        assert node_to_flavor == {
            ("node-0", "nvidia.com/mig-2g.10gb"): "A100 partition (10 GB)",
            ("node-0", "nvidia.com/mig-3g.20gb"): "A100 partition (20 GB)",
            ("node-1", "nvidia.com/mig-2g.10gb"): "A100 partition (10 GB)",
            ("node-1", "nvidia.com/mig-3g.20gb"): "A100 partition (20 GB)",
        }

    def test_node_status_not_ready(self):
        gpus, node_to_flavor = {}, {}
        self._process_partitions(gpus, node_to_flavor, "node-0", allocatable={})

        assert gpus == {}
        assert node_to_flavor == {}
