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

    def info(self, *args, **kwargs):
        pass

    def warning(self, msg, *args, **kwargs):
        self.warnings.append(msg)

    def error(self, *args, **kwargs):
        pass


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
