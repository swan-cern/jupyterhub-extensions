"""
Unit tests for AvailableGPUs in _gpuinfo.py.

AvailableGPUs.__init__ calls config.load_incluster_config(), so we bypass it
by subclassing and skipping __init__, then calling methods directly on instances.
"""

from threading import Lock

from swanspawner._gpuinfo import AvailableGPUs, _GPUInfo

EVENTS_ROLE = 'swan-events'
LHCB_ROLE = 'swan-lhcb'


class _MockGPUs(AvailableGPUs):
    """Bypasses __init__ so tests can run without a Kubernetes cluster."""

    def __init__(self, node_to_flavor=None, gpus=None, cordoned=None, lhcb_nodes=None, events_nodes=None):
        self._events_role = EVENTS_ROLE
        self._lhcb_role = LHCB_ROLE
        self._gpus = gpus or {}
        self._node_to_flavor = node_to_flavor or {}
        self._cordoned_gpu_nodes = cordoned or []
        self._lhcb_nodes = lhcb_nodes or set()
        self._events_nodes = events_nodes or set()
        self._lock = Lock()


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

# Three-node cluster: one standard, one LHCb-labelled, one events-labelled.
_NODE_TO_FLAVOR = {
    ('node-std',    'nvidia.com/gpu'): 'Tesla T4 (16 GB)',
    ('node-lhcb',   'nvidia.com/gpu'): 'A100 (40 GB)',
    ('node-events', 'nvidia.com/gpu'): 'Tesla T4 (16 GB)',
}
_GPUS = {
    'Tesla T4 (16 GB)': _GPUInfo('nvidia.com/gpu', 'NVIDIA-T4-16GB',   count=4, free=2),
    'A100 (40 GB)':     _GPUInfo('nvidia.com/gpu', 'NVIDIA-A100-40GB', count=2, free=0),
}


def _cluster(cordoned=None):
    return _MockGPUs(
        node_to_flavor=_NODE_TO_FLAVOR,
        gpus=_GPUS,
        cordoned=cordoned or [],
        lhcb_nodes={'node-lhcb'},
        events_nodes={'node-events'},
    )


# ---------------------------------------------------------------------------
# TestGetSimplifiedGpuModel
# ---------------------------------------------------------------------------

class TestGetSimplifiedGpuModel:
    def _call(self, product_name):
        return AvailableGPUs._get_simplified_gpu_model(_MockGPUs(), product_name)

    def test_t4_product_returns_tesla_t4(self):
        assert self._call('NVIDIA-T4-16GB') == 'Tesla T4'

    def test_a100_product_returns_a100(self):
        assert self._call('NVIDIA-A100-PCIE-40GB') == 'A100'

    def test_unknown_product_returned_unchanged(self):
        assert self._call('NVIDIA-H100-SXM5-80GB') == 'NVIDIA-H100-SXM5-80GB'

    def test_t4_substring_anywhere_matches(self):
        assert self._call('Some-T4-Variant') == 'Tesla T4'

    def test_a100_substring_anywhere_matches(self):
        assert self._call('A100-SXM4-40GB') == 'A100'


# ---------------------------------------------------------------------------
# TestRoleFlags
# ---------------------------------------------------------------------------

class TestRoleFlags:
    def _call(self, roles):
        return AvailableGPUs._role_flags(_MockGPUs(), roles)

    def test_no_special_role_is_normal(self):
        is_lhcb, is_events, is_normal = self._call(['some-other-role'])
        assert not is_lhcb
        assert not is_events
        assert is_normal

    def test_empty_roles_is_normal(self):
        _is_lhcb, _is_events, is_normal = self._call([])
        assert is_normal

    def test_lhcb_role_detected(self):
        is_lhcb, is_events, is_normal = self._call([LHCB_ROLE])
        assert is_lhcb
        assert not is_events
        assert not is_normal

    def test_events_role_detected(self):
        is_lhcb, is_events, is_normal = self._call([EVENTS_ROLE])
        assert not is_lhcb
        assert is_events
        assert not is_normal

    def test_both_roles_not_normal(self):
        is_lhcb, is_events, is_normal = self._call([LHCB_ROLE, EVENTS_ROLE])
        assert is_lhcb
        assert is_events
        assert not is_normal


# ---------------------------------------------------------------------------
# TestGetAllowedFlavorsForRole
# ---------------------------------------------------------------------------

class TestGetAllowedFlavorsForRole:
    def _call(self, mock, is_lhcb, is_events, is_normal):
        return AvailableGPUs._get_allowed_flavors_for_role(mock, is_lhcb, is_events, is_normal)

    def test_normal_user_sees_only_standard_node(self):
        flavors = self._call(_cluster(), is_lhcb=False, is_events=False, is_normal=True)
        assert flavors == {'Tesla T4 (16 GB)'}

    def test_lhcb_user_sees_standard_and_lhcb_nodes(self):
        flavors = self._call(_cluster(), is_lhcb=True, is_events=False, is_normal=False)
        assert flavors == {'Tesla T4 (16 GB)', 'A100 (40 GB)'}

    def test_events_user_sees_only_events_node(self):
        flavors = self._call(_cluster(), is_lhcb=False, is_events=True, is_normal=False)
        assert flavors == {'Tesla T4 (16 GB)'}

    def test_lhcb_user_does_not_see_events_node(self):
        # node-events has the events label, so LHCb users must not see it
        flavors = self._call(_cluster(), is_lhcb=True, is_events=False, is_normal=False)
        # both Tesla T4 sources: node-std (allowed) and node-events (blocked for lhcb)
        # A100 from node-lhcb (allowed for lhcb)
        assert 'A100 (40 GB)' in flavors

    def test_cordoned_node_excluded_for_normal_user(self):
        mock = _cluster(cordoned=['node-std'])
        flavors = self._call(mock, is_lhcb=False, is_events=False, is_normal=True)
        assert flavors == set()

    def test_cordoned_lhcb_node_excluded_for_lhcb_user(self):
        mock = _cluster(cordoned=['node-lhcb'])
        flavors = self._call(mock, is_lhcb=True, is_events=False, is_normal=False)
        assert 'A100 (40 GB)' not in flavors


# ---------------------------------------------------------------------------
# TestGetAvailableGpuFlavours
# ---------------------------------------------------------------------------

class TestGetAvailableGpuFlavours:
    def test_normal_user_gets_standard_gpu(self):
        result = _cluster().get_available_gpu_flavours([])
        assert list(result.keys()) == ['Tesla T4 (16 GB)']

    def test_lhcb_user_gets_both_gpus(self):
        result = _cluster().get_available_gpu_flavours([LHCB_ROLE])
        assert set(result.keys()) == {'Tesla T4 (16 GB)', 'A100 (40 GB)'}

    def test_returned_values_are_gpu_info_objects(self):
        result = _cluster().get_available_gpu_flavours([])
        assert isinstance(result['Tesla T4 (16 GB)'], _GPUInfo)


# ---------------------------------------------------------------------------
# TestGetFreeGpuFlavours
# ---------------------------------------------------------------------------

class TestGetFreeGpuFlavours:
    def test_normal_user_sees_only_flavours_with_free_count(self):
        # Tesla T4: free=2, A100: free=0 (but A100 is lhcb-only anyway)
        result = _cluster().get_free_gpu_flavours([])
        assert 'Tesla T4 (16 GB)' in result

    def test_lhcb_user_excluded_a100_because_none_free(self):
        result = _cluster().get_free_gpu_flavours([LHCB_ROLE])
        assert 'A100 (40 GB)' not in result
        assert 'Tesla T4 (16 GB)' in result

    def test_no_free_gpus_returns_empty(self):
        no_free_gpus = {
            'Tesla T4 (16 GB)': _GPUInfo('nvidia.com/gpu', 'NVIDIA-T4', count=2, free=0),
        }
        mock = _MockGPUs(
            node_to_flavor={('node-std', 'nvidia.com/gpu'): 'Tesla T4 (16 GB)'},
            gpus=no_free_gpus,
        )
        result = mock.get_free_gpu_flavours([])
        assert result == {}
