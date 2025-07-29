"""
Comprehensive integration tests for the Orac class.

These tests verify the full flow from YAML loading through API calls,
testing real parameter resolution, file handling, and response processing.
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from orac.orac import Orac


class TestOracIntegration:
    """Integration tests for the complete Orac flow."""

    @pytest.mark.integration
    @patch('orac.orac.call_api')
    def test_basic_prompt_flow(self, mock_call_api, test_prompts_dir):
        """Test complete flow with basic prompt."""
        mock_call_api.return_value = "Paris"
        
        orac = Orac("capital", prompts_dir=str(test_prompts_dir))
        result = orac.completion(country="France")
        
        assert result == "Paris"
        
        # Verify the API was called with proper parameters
        mock_call_api.assert_called_once()
        call_kwargs = mock_call_api.call_args[1]
        
        # Check that the prompt was properly templated in message_history
        message_history = call_kwargs['message_history']
        assert any("What is the capital of France?" in msg.get('text', '') 
                  for msg in message_history)

    @pytest.mark.integration
    @patch('orac.orac.call_api')
    def test_parameter_type_conversion(self, mock_call_api, temp_dir):
        """Test parameter type conversion and validation."""
        mock_call_api.return_value = "Converted successfully"
        
        # Create a prompt with different parameter types
        prompts_dir = temp_dir / "prompts"
        prompts_dir.mkdir()
        
        (prompts_dir / "types_test.yaml").write_text("""
prompt: "Number: ${number}, Flag: ${flag}, Items: ${items}"
parameters:
  - name: number
    type: int
    default: 42
  - name: flag
    type: bool
    default: true
  - name: items
    type: list
    default: "a,b,c"
""")
        
        orac = Orac("types_test", prompts_dir=str(prompts_dir))
        result = orac.completion(number="100", flag="false", items="x,y,z")
        
        assert result == "Converted successfully"
        
        # Verify parameters were converted correctly in the prompt
        call_kwargs = mock_call_api.call_args[1]
        message_history = call_kwargs['message_history']
        prompt_content = message_history[0]['text']
        assert "Number: 100" in prompt_content
        assert "Flag: False" in prompt_content
        assert "Items: ['x', 'y', 'z']" in prompt_content

    @pytest.mark.integration
    @patch('orac.orac.call_api')
    def test_json_response_flow(self, mock_call_api, test_prompts_dir):
        """Test JSON response handling flow."""
        mock_response = {
            "title": "Chocolate Chip Cookies",
            "ingredients": ["flour", "sugar", "chocolate chips"],
            "time": "30 minutes"
        }
        mock_call_api.return_value = json.dumps(mock_response)
        
        orac = Orac("recipe", prompts_dir=str(test_prompts_dir))
        
        # Test completion_as_json method
        result_json = orac.completion_as_json(dish="cookies")
        assert result_json == mock_response
        assert isinstance(result_json, dict)
        
        # Test callable interface auto-detection
        result_auto = orac(dish="cookies")
        assert result_auto == mock_response
        assert isinstance(result_auto, dict)

    @pytest.mark.integration
    @patch('orac.orac.call_api')
    def test_file_attachment_flow(self, mock_call_api, temp_dir):
        """Test file attachment and processing flow."""
        mock_call_api.return_value = "File processed successfully"
        
        # Create test files
        test_file = temp_dir / "test.txt"
        test_file.write_text("This is test content for processing.")
        
        prompts_dir = temp_dir / "prompts"
        prompts_dir.mkdir()
        
        (prompts_dir / "file_prompt.yaml").write_text("""
prompt: "Process this file"
files:
  - "*.txt"
""")
        
        # Use files constructor parameter for file attachment
        orac = Orac("file_prompt", prompts_dir=str(prompts_dir), files=[str(test_file)])
        result = orac.completion()
        
        assert result == "File processed successfully"
        
        # Verify file content was included in the API call
        call_kwargs = mock_call_api.call_args[1]
        
        # Check if files were passed to call_api
        file_paths = call_kwargs.get('file_paths', [])
        assert len(file_paths) > 0
        assert str(test_file) in file_paths

    @pytest.mark.integration
    @patch('orac.orac.call_api')
    def test_parameter_defaults_and_overrides(self, mock_call_api, test_prompts_dir):
        """Test parameter default values and overrides."""
        mock_call_api.return_value = "Parameter test completed"
        
        orac = Orac("capital", prompts_dir=str(test_prompts_dir))
        
        # Test with default parameter
        result_default = orac.completion()
        call_kwargs_default = mock_call_api.call_args[1]
        default_history = call_kwargs_default['message_history']
        default_prompt = default_history[0]['text']
        assert "France" in default_prompt  # Default country from fixture
        
        mock_call_api.reset_mock()
        
        # Test with override parameter
        result_override = orac.completion(country="Japan")
        call_kwargs_override = mock_call_api.call_args[1]
        override_history = call_kwargs_override['message_history']
        override_prompt = override_history[0]['text']
        assert "Japan" in override_prompt

    @pytest.mark.integration
    @patch('orac.orac.call_api')
    def test_configuration_merging(self, mock_call_api, temp_dir):
        """Test configuration merging from YAML and constructor args."""
        mock_call_api.return_value = "Config test completed"
        
        prompts_dir = temp_dir / "prompts"
        prompts_dir.mkdir()
        
        (prompts_dir / "config_test.yaml").write_text("""
prompt: "Test: ${param}"
parameters:
  - name: param
    type: string
    default: "yaml_default"
model_name: "gemini-1.5-pro"
generation_config:
  temperature: 0.5
  max_output_tokens: 100
""")
        
        # Test with constructor overrides
        orac = Orac(
            "config_test", 
            prompts_dir=str(prompts_dir),
            model_name="gemini-2.0-flash-001",
            generation_config={"temperature": 0.8}
        )
        
        result = orac.completion(param="test_value")
        
        # Verify configuration was properly merged
        call_kwargs = mock_call_api.call_args[1]
        assert call_kwargs['model_name'] == "gemini-2.0-flash-001"  # Constructor override
        
        # Check generation_config was merged
        gen_config = call_kwargs.get('generation_config', {})
        assert gen_config.get('temperature') == 0.8  # Constructor override
        assert gen_config.get('max_output_tokens') == 100  # From YAML (not overridden)

    @pytest.mark.integration
    @patch('orac.orac.call_api')
    def test_error_handling_invalid_json(self, mock_call_api, test_prompts_dir):
        """Test error handling for invalid JSON responses."""
        mock_call_api.return_value = "Not valid JSON response"
        
        orac = Orac("recipe", prompts_dir=str(test_prompts_dir))
        
        # completion_as_json should raise JSONDecodeError for invalid JSON
        with pytest.raises(json.JSONDecodeError):
            orac.completion_as_json(dish="pasta")
        
        # Callable interface with force_json should also raise
        with pytest.raises(ValueError, match="Response is not valid JSON"):
            orac(dish="pasta", force_json=True)
        
        # But callable interface without force_json should return string
        result = orac(dish="pasta")
        assert result == "Not valid JSON response"
        assert isinstance(result, str)

    @pytest.mark.integration
    @patch('orac.orac.call_api')
    def test_glob_pattern_file_resolution(self, mock_call_api, temp_dir):
        """Test glob pattern resolution for file parameters."""
        mock_call_api.return_value = "Multiple files processed"
        
        # Create multiple test files
        files_dir = temp_dir / "files"
        files_dir.mkdir()
        
        (files_dir / "file1.txt").write_text("Content 1")
        (files_dir / "file2.txt").write_text("Content 2")
        (files_dir / "other.log").write_text("Log content")
        
        prompts_dir = temp_dir / "prompts"
        prompts_dir.mkdir()
        
        # Create YAML with glob pattern for file selection
        (prompts_dir / "multi_file.yaml").write_text(f"""
prompt: "Process these files"
files:
  - "{files_dir}/*.txt"
""")
        
        orac = Orac("multi_file", prompts_dir=str(prompts_dir))
        result = orac.completion()
        
        assert result == "Multiple files processed"
        
        # Verify that multiple files were attached
        call_kwargs = mock_call_api.call_args[1]
        file_paths = call_kwargs.get('file_paths', [])
        
        # Should have 2 .txt files, not the .log file
        txt_files = [f for f in file_paths if f.endswith('.txt')]
        assert len(txt_files) == 2

    @pytest.mark.integration
    def test_prompt_not_found_error(self, temp_dir):
        """Test error handling when prompt file is not found."""
        prompts_dir = temp_dir / "prompts"
        prompts_dir.mkdir()
        
        with pytest.raises(FileNotFoundError):
            orac = Orac("nonexistent_prompt", prompts_dir=str(prompts_dir))
            orac.completion()

    @pytest.mark.integration
    @patch('orac.orac.call_api')
    def test_parameter_info_retrieval(self, mock_call_api, test_prompts_dir):
        """Test parameter information retrieval."""
        orac = Orac("capital", prompts_dir=str(test_prompts_dir))
        
        param_info = orac.get_parameter_info()
        
        assert isinstance(param_info, list)
        assert len(param_info) > 0
        
        # Should have country parameter from fixture
        country_param = next((p for p in param_info if p['name'] == 'country'), None)
        assert country_param is not None
        assert country_param['type'] == 'string'
        assert country_param['default'] == 'France'


class TestOracAdvancedFeatures:
    """Test advanced Orac features and edge cases."""

    @pytest.mark.integration
    @patch('orac.orac.call_api')
    def test_template_string_resolution(self, mock_call_api, temp_dir):
        """Test complex template string resolution with nested variables."""
        mock_call_api.return_value = "Template resolved"
        
        prompts_dir = temp_dir / "prompts"
        prompts_dir.mkdir()
        
        (prompts_dir / "complex_template.yaml").write_text("""
prompt: |
  Task: ${task}
  Context: ${context}
  Format: ${format}
  Additional info: ${task} should be done in ${format} format.
parameters:
  - name: task
    type: string
    default: "summarize"
  - name: context
    type: string
    default: "document"
  - name: format
    type: string
    default: "JSON"
""")
        
        orac = Orac("complex_template", prompts_dir=str(prompts_dir))
        result = orac.completion(task="analyze", context="code", format="markdown")
        
        call_kwargs = mock_call_api.call_args[1]
        message_history = call_kwargs['message_history']
        prompt_content = message_history[0]['text']
        
        # Verify all template variables were resolved
        assert "Task: analyze" in prompt_content
        assert "Context: code" in prompt_content  
        assert "Format: markdown" in prompt_content
        assert "analyze should be done in markdown format" in prompt_content

    @pytest.mark.integration
    @patch('orac.orac.call_api')
    def test_empty_and_none_parameters(self, mock_call_api, temp_dir):
        """Test handling of empty and None parameter values."""
        mock_call_api.return_value = "Empty params handled"
        
        prompts_dir = temp_dir / "prompts"
        prompts_dir.mkdir()
        
        (prompts_dir / "empty_test.yaml").write_text("""
prompt: "Value: '${value}', Optional: '${optional}'"
parameters:
  - name: value
    type: string
    default: ""
  - name: optional
    type: string
    required: false
""")
        
        orac = Orac("empty_test", prompts_dir=str(prompts_dir))
        
        # Test with empty string
        result = orac.completion(value="", optional=None)
        
        call_kwargs = mock_call_api.call_args[1]
        message_history = call_kwargs['message_history']
        prompt_content = message_history[0]['text']
        
        # Should handle empty values gracefully
        assert "Value: ''" in prompt_content