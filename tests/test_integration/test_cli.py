"""
CLI integration tests for essential functionality.

These tests focus on the core CLI features that users rely on most:
- Basic prompt execution
- Parameter passing
- Help/info functionality
- Error handling
"""

import pytest
import sys
import json
from unittest.mock import patch
from pathlib import Path

from orac.cli import main as cli


class TestCLI:
    """Tests for core CLI functionality."""

    @pytest.mark.integration
    @patch('orac.prompt.call_api')
    def test_basic_prompt_execution(self, mock_call_api, test_prompts_dir, monkeypatch, capsys):
        """Test basic prompt execution via CLI."""
        mock_call_api.return_value = "Paris"
        
        # Mock sys.argv to simulate CLI call
        args = ["orac", "capital", "--prompts-dir", str(test_prompts_dir)]
        monkeypatch.setattr(sys, 'argv', args)
        
        # CLI should run successfully without raising SystemExit
        cli.main()
        
        # Check output
        captured = capsys.readouterr()
        assert "Paris" in captured.out

    @pytest.mark.integration
    @patch('orac.prompt.call_api')
    def test_prompt_with_parameters(self, mock_call_api, test_prompts_dir, monkeypatch, capsys):
        """Test prompt execution with custom parameters."""
        mock_call_api.return_value = "Tokyo"
        
        args = ["orac", "capital", "--prompts-dir", str(test_prompts_dir), "--country", "Japan"]
        monkeypatch.setattr(sys, 'argv', args)
        
        cli.main()
        
        captured = capsys.readouterr()
        assert "Tokyo" in captured.out

    @pytest.mark.integration
    def test_info_functionality(self, test_prompts_dir, monkeypatch, capsys):
        """Test prompt show command shows parameter information."""
        args = ["orac", "prompt", "show", "capital", "--prompts-dir", str(test_prompts_dir)]
        monkeypatch.setattr(sys, 'argv', args)
        
        cli.main()
        
        captured = capsys.readouterr()
        
        # Should show parameter info without making API calls
        assert "Parameters" in captured.out or "country" in captured.out

    @pytest.mark.integration
    @patch('orac.prompt.call_api')
    def test_json_response_handling(self, mock_call_api, test_prompts_dir, monkeypatch, capsys):
        """Test CLI handling of JSON responses."""
        mock_response = {"title": "Pasta Recipe", "time": "20 minutes"}
        mock_call_api.return_value = json.dumps(mock_response)
        
        args = ["orac", "recipe", "--prompts-dir", str(test_prompts_dir)]
        monkeypatch.setattr(sys, 'argv', args)
        
        cli.main()
        
        captured = capsys.readouterr()
        
        # Should output the JSON response
        assert "Pasta Recipe" in captured.out

    @pytest.mark.integration
    def test_nonexistent_prompt_error(self, test_prompts_dir, monkeypatch, capsys):
        """Test error handling for nonexistent prompts."""
        args = ["orac", "nonexistent_prompt", "--prompts-dir", str(test_prompts_dir)]
        monkeypatch.setattr(sys, 'argv', args)
        
        with pytest.raises(SystemExit) as excinfo:
            cli.main()
        
        # Should exit with non-zero code
        assert excinfo.value.code != 0
        captured = capsys.readouterr()
        
        # Should show error message
        assert "not found" in captured.err.lower() or "error" in captured.err.lower()

    @pytest.mark.integration  
    def test_verbose_mode(self, test_prompts_dir, monkeypatch, capsys):
        """Test verbose output mode via console logging.""" 
        
        # Set prompts dir via monkeypatch to work around CLI argument parsing issues
        monkeypatch.setattr('orac.config.Config.DEFAULT_PROMPTS_DIR', str(test_prompts_dir))
        
        # Test that verbose logging configuration works with loguru
        from orac.logger import configure_console_logging, logger
        
        # Test verbose=True adds console handler
        configure_console_logging(verbose=True)
        logger.info("Test verbose message")
        captured = capsys.readouterr()
        assert "Test verbose message" in captured.err
        
        # Test verbose=False removes console handler
        configure_console_logging(verbose=False)
        logger.info("Test non-verbose message") 
        captured = capsys.readouterr()
        assert captured.err == ""  # Should be empty in non-verbose mode


class TestCLIErrorHandling:
    """CLI error handling tests."""

    @pytest.mark.integration
    def test_missing_required_env_graceful_failure(self, test_prompts_dir, monkeypatch, capsys):
        """Test that missing API key fails gracefully."""
        # Remove API key environment variable
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
        monkeypatch.delenv("ORAC_LLM_PROVIDER", raising=False)
        
        args = ["orac", "capital", "--prompts-dir", str(test_prompts_dir)]
        monkeypatch.setattr(sys, 'argv', args)
        
        with pytest.raises(SystemExit) as excinfo:
            cli.main()
        
        # Should fail gracefully with non-zero exit code
        assert excinfo.value.code != 0
        
        # Should show helpful error message
        captured = capsys.readouterr()
        error_output = captured.err.lower()
        assert any(word in error_output for word in ["provider", "api", "key", "environment"])

    @pytest.mark.integration
    def test_invalid_argument_handling(self, test_prompts_dir, monkeypatch, capsys):
        """Test handling of invalid CLI arguments."""
        # Use an invalid flag
        args = ["orac", "capital", "--invalid-flag", "value"]
        monkeypatch.setattr(sys, 'argv', args)
        
        with pytest.raises(SystemExit) as excinfo:
            cli.main()
        
        # Should exit with non-zero code
        assert excinfo.value.code != 0