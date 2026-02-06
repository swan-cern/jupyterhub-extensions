"""
Unit tests for swanspawner.py functions
"""

import pytest
import os
from swanspawner.swanspawner import get_repo_name_from_options

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
