"""
Unit tests for the test skill.
"""

import pytest
import json
from unittest.mock import patch, MagicMock

from orac.skills.test import execute, _build_prompt, _parse_results, _normalize_results


class TestTestSkill:
    """Unit tests for the test skill."""

    @pytest.mark.unit
    def test_empty_requirements_returns_empty_results(self):
        """Test that empty requirements list returns empty results."""
        result = execute({
            'requirements': [],
            'working_directory': '/tmp'
        })

        assert result['results'] == []
        assert result['summary']['total'] == 0
        assert result['all_passed'] is True

    @pytest.mark.unit
    def test_execute_calls_code_skill(self):
        """Test that execute calls the code skill correctly."""
        mock_response = json.dumps([
            {'requirement': 'Test 1', 'status': 'PASS'},
            {'requirement': 'Test 2', 'status': 'FAIL', 'info': 'Failed check'}
        ])

        with patch('orac.skills.test.code_execute') as mock_code:
            mock_code.return_value = {'result': mock_response}

            result = execute({
                'requirements': ['Test 1', 'Test 2'],
                'working_directory': '/tmp/test'
            })

            mock_code.assert_called_once()
            call_args = mock_code.call_args[0][0]
            assert call_args['working_directory'] == '/tmp/test'
            assert 'Test 1' in call_args['prompt']
            assert 'Test 2' in call_args['prompt']

    @pytest.mark.unit
    def test_execute_parses_pass_results(self):
        """Test that PASS results are parsed correctly."""
        mock_response = json.dumps([
            {'requirement': 'Feature works', 'status': 'PASS'}
        ])

        with patch('orac.skills.test.code_execute') as mock_code:
            mock_code.return_value = {'result': mock_response}

            result = execute({
                'requirements': ['Feature works'],
                'working_directory': '/tmp'
            })

            assert result['results'][0]['status'] == 'PASS'
            assert result['summary']['passed'] == 1
            assert result['summary']['failed'] == 0
            assert result['all_passed'] is True

    @pytest.mark.unit
    def test_execute_parses_fail_results(self):
        """Test that FAIL results are parsed correctly."""
        mock_response = json.dumps([
            {'requirement': 'Feature works', 'status': 'FAIL', 'info': 'Broken'}
        ])

        with patch('orac.skills.test.code_execute') as mock_code:
            mock_code.return_value = {'result': mock_response}

            result = execute({
                'requirements': ['Feature works'],
                'working_directory': '/tmp'
            })

            assert result['results'][0]['status'] == 'FAIL'
            assert result['results'][0]['info'] == 'Broken'
            assert result['summary']['passed'] == 0
            assert result['summary']['failed'] == 1
            assert result['all_passed'] is False

    @pytest.mark.unit
    def test_execute_passes_agent_options(self):
        """Test that agent options are passed through."""
        mock_response = json.dumps([{'requirement': 'Test', 'status': 'PASS'}])

        with patch('orac.skills.test.code_execute') as mock_code:
            mock_code.return_value = {'result': mock_response}

            execute({
                'requirements': ['Test'],
                'working_directory': '/tmp',
                'agent': 'codex',
                'model': 'o3',
                'api_endpoint': 'https://api.example.com',
                'api_key': 'sk-test'
            })

            call_args = mock_code.call_args[0][0]
            assert call_args['agent'] == 'codex'
            assert call_args['model'] == 'o3'
            assert call_args['api_endpoint'] == 'https://api.example.com'
            assert call_args['api_key'] == 'sk-test'

    @pytest.mark.unit
    def test_build_prompt_includes_requirements(self):
        """Test that build_prompt includes all requirements."""
        prompt = _build_prompt(['Req 1', 'Req 2', 'Req 3'], None)

        assert '1. Req 1' in prompt
        assert '2. Req 2' in prompt
        assert '3. Req 3' in prompt

    @pytest.mark.unit
    def test_build_prompt_includes_context(self):
        """Test that build_prompt includes context when provided."""
        prompt = _build_prompt(['Req 1'], 'This is a web application')

        assert 'This is a web application' in prompt
        assert 'Context:' in prompt

    @pytest.mark.unit
    def test_build_prompt_no_context_section_when_none(self):
        """Test that context section is omitted when context is None."""
        prompt = _build_prompt(['Req 1'], None)

        assert 'Context:' not in prompt

    @pytest.mark.unit
    def test_parse_results_extracts_json(self):
        """Test that parse_results extracts JSON from output."""
        raw = 'Some text before [{"requirement": "Test", "status": "PASS"}] after'
        results = _parse_results(raw, ['Test'])

        assert len(results) == 1
        assert results[0]['status'] == 'PASS'

    @pytest.mark.unit
    def test_parse_results_handles_markdown_json(self):
        """Test that parse_results handles JSON in markdown blocks."""
        raw = '''```json
[{"requirement": "Test", "status": "PASS"}]
```'''
        results = _parse_results(raw, ['Test'])

        assert len(results) == 1
        assert results[0]['status'] == 'PASS'

    @pytest.mark.unit
    def test_parse_results_handles_invalid_json(self):
        """Test that parse_results handles invalid JSON gracefully."""
        raw = 'This is not JSON at all'
        results = _parse_results(raw, ['Test 1', 'Test 2'])

        assert len(results) == 2
        assert all(r['status'] == 'FAIL' for r in results)
        assert all('Failed to parse' in r['info'] for r in results)

    @pytest.mark.unit
    def test_normalize_results_handles_missing_items(self):
        """Test that normalize handles fewer results than requirements."""
        parsed = [{'requirement': 'Test 1', 'status': 'PASS'}]
        requirements = ['Test 1', 'Test 2', 'Test 3']

        results = _normalize_results(parsed, requirements)

        assert len(results) == 3
        assert results[0]['status'] == 'PASS'
        assert results[1]['status'] == 'FAIL'
        assert 'not evaluated' in results[1]['info']
        assert results[2]['status'] == 'FAIL'

    @pytest.mark.unit
    def test_normalize_results_adds_info_to_fail_without_info(self):
        """Test that FAIL without info gets default info."""
        parsed = [{'requirement': 'Test', 'status': 'FAIL'}]
        requirements = ['Test']

        results = _normalize_results(parsed, requirements)

        assert results[0]['info'] == 'No failure details provided'

    @pytest.mark.unit
    def test_normalize_results_preserves_pass_info(self):
        """Test that PASS with info preserves the info."""
        parsed = [{'requirement': 'Test', 'status': 'PASS', 'info': 'Verified via unit test'}]
        requirements = ['Test']

        results = _normalize_results(parsed, requirements)

        assert results[0]['info'] == 'Verified via unit test'

    @pytest.mark.unit
    def test_normalize_results_fixes_lowercase_status(self):
        """Test that lowercase status is normalized."""
        parsed = [{'requirement': 'Test', 'status': 'pass'}]
        requirements = ['Test']

        results = _normalize_results(parsed, requirements)

        assert results[0]['status'] == 'PASS'

    @pytest.mark.unit
    def test_normalize_results_invalid_status_becomes_fail(self):
        """Test that invalid status becomes FAIL."""
        parsed = [{'requirement': 'Test', 'status': 'MAYBE'}]
        requirements = ['Test']

        results = _normalize_results(parsed, requirements)

        assert results[0]['status'] == 'FAIL'

    @pytest.mark.unit
    def test_summary_counts_correct(self):
        """Test that summary counts are calculated correctly."""
        mock_response = json.dumps([
            {'requirement': 'R1', 'status': 'PASS'},
            {'requirement': 'R2', 'status': 'PASS'},
            {'requirement': 'R3', 'status': 'FAIL', 'info': 'Error'},
            {'requirement': 'R4', 'status': 'PASS'},
            {'requirement': 'R5', 'status': 'FAIL', 'info': 'Error'}
        ])

        with patch('orac.skills.test.code_execute') as mock_code:
            mock_code.return_value = {'result': mock_response}

            result = execute({
                'requirements': ['R1', 'R2', 'R3', 'R4', 'R5'],
                'working_directory': '/tmp'
            })

            assert result['summary']['passed'] == 3
            assert result['summary']['failed'] == 2
            assert result['summary']['total'] == 5
            assert result['all_passed'] is False
