"""
Unit tests for swanspawner.py functions
"""

import os

import pytest
from swanspawner.swanspawner import define_SwanSpawner_from, get_repo_name_from_options

_SwanSpawner = define_SwanSpawner_from(object)


class _MockLog:
    def __init__(self):
        self.warnings = []
        self.errors = []

    def info(self, *args, **kwargs):
        pass

    def warning(self, msg, *args, **kwargs):
        self.warnings.append(msg)

    def error(self, msg, *args, **kwargs):
        self.errors.append(msg)


class _MockSpawner:
    """Minimal stand-in; provides the class-level string constants and a log."""

    rucio_instance = 'rucio'
    rucio_rse = 'rucioRSE'
    rucio_rse_mount_path = 'rse_mount_path'
    rucio_path_begins_at = 'path_begins_at'

    def __init__(self):
        self.log = _MockLog()


def _call_validate_rucio(selection, options):
    mock = _MockSpawner()
    result = _SwanSpawner._validate_rucio_options(mock, selection, options)
    return result, mock.log


class _MockSpawnerForSelection(_MockSpawner):
    """Extends _MockSpawner with tracked _validate_rucio_options and real _popup_error."""

    def __init__(self):
        super().__init__()
        self.rucio_calls = []

    def _validate_rucio_options(self, selection, options):
        self.rucio_calls.append((selection, options))

    _popup_error = _SwanSpawner._popup_error


def _call_validate_selection(selection, options):
    mock = _MockSpawnerForSelection()
    _SwanSpawner._validate_selection_options(mock, selection, options)
    return mock


# All plain string constants from SwanSpawner — copied to avoid traitlet descriptor issues
# (options_form_config / stacks_for_customenvs are traitlets, so we can't inherit and must
# set them as plain instance attributes on a standalone class).
class _MockSpawnerForForm:
    software_source = 'software_source'
    builder = 'builder'
    builder_version = 'builder_version'
    repository = 'repository'
    lcg_rel_field = 'lcg'
    use_local_packages_field = 'use-local-packages'
    platform_field = 'platforms'
    user_script_env_field = 'scriptenv'
    user_n_cores = 'cores'
    user_memory = 'memory'
    gpu = 'gpu'
    use_jupyterlab_field = 'use-jupyterlab'
    spark_cluster_field = 'clusters'
    condor_pool = 'condor'
    rucio_instance = 'rucio'
    rucio_rse = 'rucioRSE'
    rucio_rse_mount_path = 'rse_mount_path'
    rucio_path_begins_at = 'path_begins_at'
    file = 'file'
    user_interface = 'user_interface'
    customenv_special_type = 'customenv'
    lcg_special_type = 'lcg'

    _get_selection = _SwanSpawner._get_selection
    _validate_selection_options = _SwanSpawner._validate_selection_options
    _popup_error = _SwanSpawner._popup_error

    def __init__(self, config_path, stacks_for_customenvs=None):
        self.log = _MockLog()
        self.options_form_config = config_path
        self.stacks_for_customenvs = stacks_for_customenvs or []
        self.offload = False


# Minimal YAML for tests — no YAML anchors, no rucio section
_FORM_YAML = """
lcg_options:
- type: "selection"
  lcg:
    value: "LCG_110_swan"
  platforms:
  - value: "x86_64-el9-gcc13-opt"
  cores:
  - value: "2"
  - value: "4"
  memory:
  - value: "8"
  - value: "16"
  clusters:
  - value: "none"
  - value: "spark"
  condor:
  - value: "none"

customenv_options:
- type: "selection"
  builder:
    value: "docker"
  cores:
  - value: "2"
  - value: "4"
  memory:
  - value: "8"
  - value: "16"
- type: "selection"
  builder:
    value: "buildkit:2.0"
  cores:
  - value: "2"
  memory:
  - value: "8"
"""


@pytest.fixture
def form_config(tmp_path):
    p = tmp_path / "options_form.yaml"
    p.write_text(_FORM_YAML)
    return str(p)


class TestGetRepoNameFromOptions:
    """Test suite for get_repo_name_from_options function"""
    PROJECT_FOLDER = "SWAN_projects"
    EXPECTED_REPO_NAME = "myproject"

    def test_no_repository_key(self):
        """Test when 'repository' key is not in user_options"""
        user_options = {}
        result = get_repo_name_from_options(user_options)
        assert result == ""

    def test_github_https_url(self):
        """Test with a GitHub HTTPS URL"""
        user_options = {'repository': 'https://github.com/user/myproject'}
        result = get_repo_name_from_options(user_options)
        assert result == os.path.join(self.PROJECT_FOLDER, self.EXPECTED_REPO_NAME)

    def test_url_with_trailing_slash(self):
        """Test URL with trailing slash"""
        user_options = {'repository': 'https://github.com/user/myproject/'}
        result = get_repo_name_from_options(user_options)
        assert result == os.path.join(self.PROJECT_FOLDER, self.EXPECTED_REPO_NAME)

    def test_github_https_url_with_git_extension(self):
        """Test with a GitHub HTTPS URL ending in .git"""
        user_options = {'repository': 'https://github.com/user/myproject.git'}
        result = get_repo_name_from_options(user_options)
        assert result == os.path.join(self.PROJECT_FOLDER, self.EXPECTED_REPO_NAME)

    def test_nested_path_structure(self):
        """Test with deeply nested repository path"""
        user_options = {'repository': 'https://gitlab.com/org/team/group/myproject.git'}
        result = get_repo_name_from_options(user_options)
        assert result == os.path.join(self.PROJECT_FOLDER, self.EXPECTED_REPO_NAME)

    def test_github_https_url_with_git_extension_and_trailing_slash(self):
        """Test with a GitHub HTTPS URL ending in .git and trailing slash"""
        user_options = {'repository': 'https://github.com/user/myproject.git/'}
        result = get_repo_name_from_options(user_options)
        assert result == os.path.join(self.PROJECT_FOLDER, self.EXPECTED_REPO_NAME)

    @pytest.mark.parametrize("repo_url,expected_name", [
        ('https://github.com/cern/swan.git', 'swan'),
        ('git@gitlab.cern.ch:swan/analysis.git', 'analysis'),
        ('https://bitbucket.org/team/data-science/', 'data-science'),
        ('simple-repo-name', 'simple-repo-name'),
        ('https://github.com/user/repo.git/', 'repo'),
    ])
    def test_various_url_formats(self, repo_url, expected_name):
        """Parameterized test for various URL formats"""
        user_options = {'repository': repo_url}
        result = get_repo_name_from_options(user_options)
        assert result == os.path.join(self.PROJECT_FOLDER, expected_name)


# ---------------------------------------------------------------------------
# TestValidateRucioOptions
# ---------------------------------------------------------------------------

class TestValidateRucioOptions:
    def test_none_instance_returns_defaults(self):
        result, _ = _call_validate_rucio({}, {'rucio': 'none'})
        assert result == {
            'rucio': 'none',
            'rucioRSE': 'none',
            'rse_mount_path': '',
            'path_begins_at': '0',
        }

    def test_missing_rucio_config_in_selection_raises(self):
        with pytest.raises(ValueError, match="Rucio configuration not found"):
            _call_validate_rucio({}, {'rucio': 'atlas'})

    def test_unknown_rucio_instance_raises(self):
        selection = {'rucio': [{'value': 'cms', 'rse_options': []}]}
        with pytest.raises(ValueError, match="Invalid Rucio instance: atlas"):
            _call_validate_rucio(selection, {'rucio': 'atlas'})

    def test_invalid_rse_raises(self):
        selection = {'rucio': [{'value': 'atlas', 'rse_options': [
            {'value': 'ATLAS_CERN', 'rse_mount_path': '/eos/atlas', 'path_begins_at': 3},
        ]}]}
        with pytest.raises(ValueError, match="Invalid RSE selection"):
            _call_validate_rucio(selection, {'rucio': 'atlas', 'rucioRSE': 'UNKNOWN_RSE'})

    def test_valid_selection_returns_correct_options(self):
        selection = {'rucio': [{'value': 'atlas', 'rse_options': [
            {'value': 'ATLAS_CERN', 'rse_mount_path': '/eos/atlas', 'path_begins_at': 3},
        ]}]}
        result, _ = _call_validate_rucio(
            selection,
            {'rucio': 'atlas', 'rucioRSE': 'ATLAS_CERN', 'rse_mount_path': '/eos/atlas', 'path_begins_at': '3'},
        )
        assert result == {
            'rucio': 'atlas',
            'rucioRSE': 'ATLAS_CERN',
            'rse_mount_path': '/eos/atlas',
            'path_begins_at': '3',
        }

    def test_missing_rse_mount_path_defaults_to_empty_string(self):
        selection = {'rucio': [{'value': 'atlas', 'rse_options': [
            {'value': 'ATLAS_CERN'},
        ]}]}
        result, _ = _call_validate_rucio(
            selection, {'rucio': 'atlas', 'rucioRSE': 'ATLAS_CERN', 'rse_mount_path': ''},
        )
        assert result['rse_mount_path'] == ''

    def test_missing_path_begins_at_defaults_to_zero_string(self):
        selection = {'rucio': [{'value': 'atlas', 'rse_options': [
            {'value': 'ATLAS_CERN', 'rse_mount_path': '/eos/atlas'},
        ]}]}
        result, _ = _call_validate_rucio(
            selection, {'rucio': 'atlas', 'rucioRSE': 'ATLAS_CERN', 'rse_mount_path': '/eos/atlas', 'path_begins_at': '0'},
        )
        assert result['path_begins_at'] == '0'

    def test_path_begins_at_int_in_config_is_returned_as_string(self):
        selection = {'rucio': [{'value': 'atlas', 'rse_options': [
            {'value': 'ATLAS_CERN', 'rse_mount_path': '/eos/atlas', 'path_begins_at': 5},
        ]}]}
        result, _ = _call_validate_rucio(
            selection, {'rucio': 'atlas', 'rucioRSE': 'ATLAS_CERN', 'rse_mount_path': '/eos/atlas', 'path_begins_at': '5'},
        )
        assert result['path_begins_at'] == '5'
        assert isinstance(result['path_begins_at'], str)

    def test_mount_path_mismatch_logs_warning(self):
        selection = {'rucio': [{'value': 'atlas', 'rse_options': [
            {'value': 'ATLAS_CERN', 'rse_mount_path': '/eos/atlas', 'path_begins_at': 3},
        ]}]}
        _, log = _call_validate_rucio(
            selection,
            {'rucio': 'atlas', 'rucioRSE': 'ATLAS_CERN', 'rse_mount_path': '/wrong/path', 'path_begins_at': '3'},
        )
        assert any('Mount path mismatch' in w for w in log.warnings)

    def test_path_begins_at_mismatch_logs_warning(self):
        selection = {'rucio': [{'value': 'atlas', 'rse_options': [
            {'value': 'ATLAS_CERN', 'rse_mount_path': '/eos/atlas', 'path_begins_at': 3},
        ]}]}
        _, log = _call_validate_rucio(
            selection,
            {'rucio': 'atlas', 'rucioRSE': 'ATLAS_CERN', 'rse_mount_path': '/eos/atlas', 'path_begins_at': '99'},
        )
        assert any('Path begins at mismatch' in w for w in log.warnings)

    def test_matching_hidden_fields_log_no_warning(self):
        selection = {'rucio': [{'value': 'atlas', 'rse_options': [
            {'value': 'ATLAS_CERN', 'rse_mount_path': '/eos/atlas', 'path_begins_at': 3},
        ]}]}
        _, log = _call_validate_rucio(
            selection,
            {'rucio': 'atlas', 'rucioRSE': 'ATLAS_CERN', 'rse_mount_path': '/eos/atlas', 'path_begins_at': '3'},
        )
        assert log.warnings == []


# ---------------------------------------------------------------------------
# TestValidateSelectionOptions
# ---------------------------------------------------------------------------

class TestValidateSelectionOptions:
    def test_empty_selection_passes(self):
        _call_validate_selection({}, {})

    def test_valid_option_passes(self):
        selection = {'cores': [{'value': '2'}, {'value': '4'}]}
        _call_validate_selection(selection, {'cores': '2'})

    def test_invalid_option_raises(self):
        selection = {'cores': [{'value': '2'}, {'value': '4'}]}
        with pytest.raises(ValueError, match="Invalid cores selection"):
            _call_validate_selection(selection, {'cores': '8'})

    def test_missing_option_raises(self):
        # options.get('cores') → None, not in valid values → _popup_error called.
        # _popup_error does options[attr] (not .get), so a missing key raises KeyError.
        selection = {'cores': [{'value': '2'}, {'value': '4'}]}
        with pytest.raises(KeyError):
            _call_validate_selection(selection, {})

    def test_non_list_attr_is_skipped(self):
        # 'type' is a string, 'lcg' is a dict — neither triggers validation
        selection = {'type': 'selection', 'lcg': {'value': 'LCG_110', 'text': '110'}}
        _call_validate_selection(selection, {})

    def test_rucio_attr_delegates_to_validate_rucio(self):
        selection = {'rucio': [{'value': 'atlas', 'rse_options': []}]}
        options = {'rucio': 'atlas'}
        mock = _call_validate_selection(selection, options)
        assert len(mock.rucio_calls) == 1
        assert mock.rucio_calls[0] == (selection, options)

    def test_rucio_sub_attrs_are_skipped(self):
        selection = {
            'rucioRSE': 'ATLAS_CERN',
            'rse_mount_path': '/eos/atlas',
            'path_begins_at': '3',
        }
        _call_validate_selection(selection, {})

    def test_multiple_valid_options_all_pass(self):
        selection = {
            'cores': [{'value': '2'}, {'value': '4'}],
            'memory': [{'value': '8'}, {'value': '16'}],
        }
        _call_validate_selection(selection, {'cores': '2', 'memory': '8'})

    def test_first_invalid_option_raises(self):
        selection = {
            'cores': [{'value': '2'}, {'value': '4'}],
            'memory': [{'value': '8'}, {'value': '16'}],
        }
        with pytest.raises(ValueError):
            _call_validate_selection(selection, {'cores': '999', 'memory': '8'})


# ---------------------------------------------------------------------------
# TestOptionsFromForm
# ---------------------------------------------------------------------------

class TestOptionsFromForm:
    @staticmethod
    def _lcg_formdata(**overrides):
        data = {
            'software_source': ['lcg'],
            'lcg': ['LCG_110_swan'],
            'platforms': ['x86_64-el9-gcc13-opt'],
            'scriptenv': ['none'],
            'condor': ['none'],
            'cores': ['2'],
            'memory': ['8'],
        }
        data.update(overrides)
        return data

    @staticmethod
    def _customenv_formdata(**overrides):
        data = {
            'software_source': ['customenv'],
            'builder': ['docker'],
            'repository': ['https://github.com/user/repo'],
            'cores': ['2'],
            'memory': ['8'],
        }
        data.update(overrides)
        return data

    def test_lcg_common_fields_extracted(self, form_config):
        mock = _MockSpawnerForForm(form_config)
        result = _SwanSpawner.options_from_form(mock, self._lcg_formdata())
        assert result['software_source'] == 'lcg'
        assert result['lcg'] == 'LCG_110_swan'
        assert result['platforms'] == 'x86_64-el9-gcc13-opt'

    def test_cores_converted_to_int(self, form_config):
        mock = _MockSpawnerForForm(form_config)
        result = _SwanSpawner.options_from_form(mock, self._lcg_formdata())
        assert result['cores'] == 2
        assert isinstance(result['cores'], int)

    def test_memory_gets_g_suffix(self, form_config):
        mock = _MockSpawnerForForm(form_config)
        result = _SwanSpawner.options_from_form(mock, self._lcg_formdata())
        assert result['memory'] == '8G'

    def test_offload_false_when_no_cluster(self, form_config):
        mock = _MockSpawnerForForm(form_config)
        _SwanSpawner.options_from_form(mock, self._lcg_formdata())
        assert mock.offload is False

    def test_offload_true_when_cluster_set(self, form_config):
        mock = _MockSpawnerForForm(form_config)
        _SwanSpawner.options_from_form(mock, self._lcg_formdata(clusters=['spark']))
        assert mock.offload is True

    def test_unknown_software_source_raises(self, form_config):
        mock = _MockSpawnerForForm(form_config)
        with pytest.raises(ValueError):
            _SwanSpawner.options_from_form(mock, self._lcg_formdata(software_source=['unknown']))

    def test_customenv_builder_and_repository_extracted(self, form_config):
        mock = _MockSpawnerForForm(form_config)
        result = _SwanSpawner.options_from_form(mock, self._customenv_formdata())
        assert result['builder'] == 'docker'
        assert result['repository'] == 'https://github.com/user/repo'

    def test_customenv_builder_version_split(self, form_config):
        mock = _MockSpawnerForForm(form_config)
        result = _SwanSpawner.options_from_form(mock, self._customenv_formdata(builder=['buildkit:2.0']))
        assert result['builder'] == 'buildkit'
        assert result['builder_version'] == '2.0'

    def test_customenv_missing_repository_raises(self, form_config):
        mock = _MockSpawnerForForm(form_config)
        formdata = self._customenv_formdata()
        del formdata['repository']
        with pytest.raises(ValueError, match="no repository specified"):
            _SwanSpawner.options_from_form(mock, formdata)

    def test_customenv_missing_repository_ok_for_stack(self, form_config):
        mock = _MockSpawnerForForm(form_config, stacks_for_customenvs=['docker'])
        formdata = self._customenv_formdata()
        del formdata['repository']
        result = _SwanSpawner.options_from_form(mock, formdata)
        assert result['builder'] == 'docker'


# ---------------------------------------------------------------------------
# TestGetSelection
# ---------------------------------------------------------------------------

_LCG_CONFIG = {
    'lcg_options': [
        {'type': 'label', 'label': {'value': 'label1', 'text': 'Recommended'}},
        {
            'type': 'selection',
            'lcg': {'value': 'LCG_110_swan'},
            'cores': [{'value': '2'}, {'value': '4'}],
        },
        {
            'type': 'selection',
            'lcg': {'value': 'LCG_111_swan'},
            'cores': [{'value': '2'}],
        },
    ],
    'customenv_options': [
        {
            'type': 'selection',
            'builder': {'value': 'docker'},
            'cores': [{'value': '2'}],
        },
    ],
}


def _call_get_selection(config, options, parent):
    mock = _MockSpawnerForForm(config_path=None)
    return _SwanSpawner._get_selection(mock, config, options, parent)


class TestGetSelection:
    def test_lcg_selection_found(self):
        options = {'software_source': 'lcg', 'lcg': 'LCG_110_swan'}
        result = _call_get_selection(_LCG_CONFIG, options, 'lcg')
        assert result['lcg']['value'] == 'LCG_110_swan'
        assert result['type'] == 'selection'

    def test_second_lcg_entry_found(self):
        options = {'software_source': 'lcg', 'lcg': 'LCG_111_swan'}
        result = _call_get_selection(_LCG_CONFIG, options, 'lcg')
        assert result['lcg']['value'] == 'LCG_111_swan'

    def test_label_entries_are_skipped(self):
        # The label entry comes first; _get_selection must skip it and find the selection
        options = {'software_source': 'lcg', 'lcg': 'LCG_110_swan'}
        result = _call_get_selection(_LCG_CONFIG, options, 'lcg')
        assert result['type'] == 'selection'

    def test_customenv_selection_found(self):
        options = {'software_source': 'customenv', 'builder': 'docker'}
        result = _call_get_selection(_LCG_CONFIG, options, 'builder')
        assert result['builder']['value'] == 'docker'

    def test_no_matching_value_raises(self):
        options = {'software_source': 'lcg', 'lcg': 'LCG_999_swan'}
        with pytest.raises(ValueError, match="Invalid lcg selection"):
            _call_get_selection(_LCG_CONFIG, options, 'lcg')

    def test_unknown_software_source_raises(self):
        options = {'software_source': 'unknown', 'lcg': 'LCG_110_swan'}
        with pytest.raises(KeyError):
            _call_get_selection(_LCG_CONFIG, options, 'lcg')
