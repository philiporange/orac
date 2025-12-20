"""
Unit tests for the code skill.
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from orac.skills.code import execute


class TestCodeSkill:
    """Unit tests for the code skill."""

    @pytest.mark.unit
    def test_execute_creates_temp_directory_when_none_provided(self):
        """Test that a temp directory is created when working_directory is not provided."""
        with patch('orac.skills.code._run_claude_code') as mock_run:
            mock_run.return_value = "test output"

            result = execute({'prompt': 'test prompt'})

            assert 'working_directory' in result
            assert result['working_directory'].startswith(tempfile.gettempdir())
            assert 'orac_code_' in result['working_directory']

    @pytest.mark.unit
    def test_execute_uses_provided_working_directory(self):
        """Test that provided working_directory is used."""
        with patch('orac.skills.code._run_claude_code') as mock_run:
            mock_run.return_value = "test output"

            with tempfile.TemporaryDirectory() as tmpdir:
                result = execute({
                    'prompt': 'test prompt',
                    'working_directory': tmpdir
                })

                assert result['working_directory'] == tmpdir

    @pytest.mark.unit
    def test_execute_default_agent_is_claude_code(self):
        """Test that claude_code is the default agent."""
        with patch('orac.skills.code._run_claude_code') as mock_run:
            mock_run.return_value = "test output"

            execute({'prompt': 'test prompt'})

            mock_run.assert_called_once()
            kwargs = mock_run.call_args.kwargs
            assert kwargs['prompt'] == 'test prompt'
            assert kwargs['model'] == 'opus'

    @pytest.mark.unit
    def test_execute_custom_model(self):
        """Test that custom model is passed through."""
        with patch('orac.skills.code._run_claude_code') as mock_run:
            mock_run.return_value = "test output"

            execute({
                'prompt': 'test prompt',
                'model': 'sonnet'
            })

            kwargs = mock_run.call_args.kwargs
            assert kwargs['model'] == 'sonnet'

    @pytest.mark.unit
    def test_execute_custom_system_prompt(self):
        """Test that custom system prompt is passed through."""
        with patch('orac.skills.code._run_claude_code') as mock_run:
            mock_run.return_value = "test output"

            execute({
                'prompt': 'test prompt',
                'system': 'You are a helpful assistant.'
            })

            kwargs = mock_run.call_args.kwargs
            assert kwargs['system'] == 'You are a helpful assistant.'

    @pytest.mark.unit
    def test_execute_unsupported_agent_raises_error(self):
        """Test that unsupported agent raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported agent"):
            execute({
                'prompt': 'test prompt',
                'agent': 'unsupported_agent'
            })

    @pytest.mark.unit
    def test_execute_aider_agent(self):
        """Test that aider agent is called correctly."""
        with patch('orac.skills.code._run_aider') as mock_run:
            mock_run.return_value = "test output"

            result = execute({
                'prompt': 'test prompt',
                'agent': 'aider'
            })

            mock_run.assert_called_once()
            assert result['result'] == "test output"

    @pytest.mark.unit
    def test_execute_codex_agent(self):
        """Test that codex agent is called correctly."""
        with patch('orac.skills.code._run_codex') as mock_run:
            mock_run.return_value = "test output"

            result = execute({
                'prompt': 'test prompt',
                'agent': 'codex'
            })

            mock_run.assert_called_once()
            assert result['result'] == "test output"

    @pytest.mark.unit
    def test_execute_goose_agent(self):
        """Test that goose agent is called correctly."""
        with patch('orac.skills.code._run_goose') as mock_run:
            mock_run.return_value = "test output"

            result = execute({
                'prompt': 'test prompt',
                'agent': 'goose'
            })

            mock_run.assert_called_once()
            assert result['result'] == "test output"

    @pytest.mark.unit
    def test_execute_system_addendum(self):
        """Test that system_addendum is passed through."""
        with patch('orac.skills.code._run_claude_code') as mock_run:
            mock_run.return_value = "test output"

            execute({
                'prompt': 'test prompt',
                'system_addendum': 'Always write tests.'
            })

            kwargs = mock_run.call_args.kwargs
            assert kwargs['system_addendum'] == 'Always write tests.'

    @pytest.mark.unit
    def test_execute_api_endpoint(self):
        """Test that api_endpoint is passed through."""
        with patch('orac.skills.code._run_claude_code') as mock_run:
            mock_run.return_value = "test output"

            execute({
                'prompt': 'test prompt',
                'api_endpoint': 'https://api.z.ai/v1'
            })

            kwargs = mock_run.call_args.kwargs
            assert kwargs['api_endpoint'] == 'https://api.z.ai/v1'

    @pytest.mark.unit
    def test_execute_api_key(self):
        """Test that api_key is passed through."""
        with patch('orac.skills.code._run_claude_code') as mock_run:
            mock_run.return_value = "test output"

            execute({
                'prompt': 'test prompt',
                'api_key': 'sk-test-key'
            })

            kwargs = mock_run.call_args.kwargs
            assert kwargs['api_key'] == 'sk-test-key'
