"""
Simplified unit tests for the Prompt class that focus on testable functionality.
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from orac.prompt import Prompt
from orac.prompt import _is_http_url, _deep_merge_dicts


class TestPromptSimple:
    """Simplified unit tests for Prompt class."""

    @pytest.mark.unit
    def test_is_http_url_function(self):
        """Test the _is_http_url helper function."""
        assert _is_http_url("http://example.com") is True
        assert _is_http_url("https://example.com") is True
        assert _is_http_url("ftp://example.com") is False
        assert _is_http_url("/local/path") is False
        assert _is_http_url("example.com") is False

    @pytest.mark.unit
    def test_deep_merge_dicts_function(self):
        """Test the _deep_merge_dicts helper function."""
        base = {"a": 1, "b": {"x": 10}}
        extra = {"b": {"y": 20}, "c": 3}
        result = _deep_merge_dicts(base, extra)
        
        expected = {"a": 1, "b": {"x": 10, "y": 20}, "c": 3}
        assert result == expected

    @pytest.mark.unit
    def test_prompt_initialization_basic(self, test_prompts_dir):
        """Test basic Prompt initialization."""
        prompt = Prompt("test_prompt", prompts_dir=str(test_prompts_dir))
        assert prompt.prompt_name == "test_prompt"
        assert prompt.prompts_root_dir == str(test_prompts_dir)

    @pytest.mark.unit
    def test_get_parameter_info(self, test_prompts_dir):
        """Test getting parameter information."""
        prompt = Prompt("test_prompt", prompts_dir=str(test_prompts_dir))
        info = prompt.get_parameter_info()
        
        assert isinstance(info, list)
        if info:  # If there are parameters defined
            assert isinstance(info[0], dict)
            assert "name" in info[0]

    @pytest.mark.unit
    @patch('orac.prompt.call_api')
    def test_completion_basic(self, mock_call_api, test_prompts_dir):
        """Test basic completion functionality."""
        mock_call_api.return_value = "Test response"
        
        prompt = Prompt("test_prompt", prompts_dir=str(test_prompts_dir))
        result = prompt.completion()
        
        assert result == "Test response"
        mock_call_api.assert_called_once()

    @pytest.mark.unit
    @patch('orac.prompt.call_api')
    def test_completion_as_json_valid(self, mock_call_api, test_prompts_dir):
        """Test completion_as_json with valid JSON."""
        mock_call_api.return_value = '{"key": "value"}'
        
        prompt = Prompt("test_prompt", prompts_dir=str(test_prompts_dir))
        result = prompt.completion_as_json()
        
        assert result == {"key": "value"}
        assert isinstance(result, dict)

    @pytest.mark.unit
    @patch('orac.prompt.call_api')
    def test_completion_as_json_invalid(self, mock_call_api, test_prompts_dir):
        """Test completion_as_json with invalid JSON."""
        mock_call_api.return_value = "Not JSON"
        
        prompt = Prompt("test_prompt", prompts_dir=str(test_prompts_dir))
        
        with pytest.raises(ValueError):
            prompt.completion_as_json()

    @pytest.mark.unit
    @patch('orac.prompt.call_api')
    def test_callable_interface(self, mock_call_api, test_prompts_dir):
        """Test the callable interface (__call__)."""
        # Test with string response
        mock_call_api.return_value = "String response"
        
        prompt = Prompt("test_prompt", prompts_dir=str(test_prompts_dir))
        result = prompt()
        
        assert result == "String response"
        assert isinstance(result, str)

    @pytest.mark.unit
    @patch('orac.prompt.call_api')
    def test_callable_interface_json_auto_detect(self, mock_call_api, test_prompts_dir):
        """Test callable interface with JSON auto-detection."""
        mock_call_api.return_value = '{"auto": "detected"}'
        
        prompt = Prompt("test_prompt", prompts_dir=str(test_prompts_dir))
        result = prompt()
        
        assert result == {"auto": "detected"}
        assert isinstance(result, dict)