"""Integration tests for teams CLI functionality."""

import pytest
import tempfile
import shutil
import yaml
from pathlib import Path
from unittest.mock import patch, Mock
from io import StringIO
import sys
import argparse

from orac.cli.team import _team_command, TeamCommand
from orac.team import TeamSpec


@pytest.fixture
def temp_test_dirs():
    """Create temporary directories with test data."""
    base_temp = tempfile.mkdtemp()
    teams_dir = Path(base_temp) / "teams"
    agents_dir = Path(base_temp) / "agents"
    teams_dir.mkdir()
    agents_dir.mkdir()

    # Create test team
    team_data = {
        'name': 'test_research_team',
        'description': 'Test research team for CLI testing',
        'leader': 'test_research_lead',
        'agents': ['test_researcher', 'test_writer'],
        'inputs': [
            {'name': 'topic', 'type': 'string', 'required': True, 'description': 'Research topic'},
            {'name': 'depth', 'type': 'string', 'default': 'standard', 'description': 'Research depth'}
        ],
        'outputs': [
            {'name': 'report', 'type': 'string', 'description': 'Research report'}
        ],
        'constitution': 'Test team constitution with research guidelines'
    }

    with open(teams_dir / "test_research_team.yaml", 'w') as f:
        yaml.dump(team_data, f)

    # Create test agents
    leader_data = {
        'name': 'Test Research Lead',
        'description': 'Test research team leader',
        'system_prompt': 'You are a test research leader',
        'inputs': [
            {'name': 'topic', 'type': 'string', 'required': True}
        ],
        'tools': ['agent:test_researcher', 'agent:test_writer', 'tool:delegate', 'tool:finish'],
        'max_iterations': 10
    }

    with open(agents_dir / "test_research_lead.yaml", 'w') as f:
        yaml.dump(leader_data, f)

    researcher_data = {
        'name': 'Test Researcher',
        'description': 'Test researcher agent',
        'system_prompt': 'You are a test researcher',
        'inputs': [
            {'name': 'task', 'type': 'string', 'required': True}
        ],
        'tools': ['tool:finish'],
        'max_iterations': 5
    }

    with open(agents_dir / "test_researcher.yaml", 'w') as f:
        yaml.dump(researcher_data, f)

    writer_data = {
        'name': 'Test Writer',
        'description': 'Test writer agent',
        'system_prompt': 'You are a test writer',
        'inputs': [
            {'name': 'task', 'type': 'string', 'required': True}
        ],
        'tools': ['tool:finish'],
        'max_iterations': 5
    }

    with open(agents_dir / "test_writer.yaml", 'w') as f:
        yaml.dump(writer_data, f)

    yield {
        'base': base_temp,
        'teams': str(teams_dir),
        'agents': str(agents_dir)
    }

    shutil.rmtree(base_temp)


def make_args(teams_dir, agents_dir=None, name=None, action=None):
    """Create mock args namespace."""
    args = argparse.Namespace()
    args.teams_dir = teams_dir
    args.agents_dir = agents_dir or "orac/agents"
    args.name = name
    args.action = action
    args.output = None
    return args


class TestTeamsList:
    """Test teams list command."""

    def test_list_teams_command(self, temp_test_dirs, capsys):
        """Test listing available teams."""
        args = make_args(temp_test_dirs['teams'])
        _team_command.handle_list(args, [])

        captured = capsys.readouterr()
        assert "Available teams" in captured.out
        assert "test_research_team" in captured.out
        assert "test_research_lead" in captured.out
        assert "Test research" in captured.out  # Partial description match since it gets truncated

    def test_list_teams_empty_directory(self, capsys):
        """Test listing teams in empty directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            args = make_args(temp_dir)
            _team_command.handle_list(args, [])

            captured = capsys.readouterr()
            assert "No teams found" in captured.out

    def test_list_teams_nonexistent_directory(self, capsys):
        """Test listing teams in nonexistent directory."""
        args = make_args("/nonexistent/directory")
        _team_command.handle_list(args, [])

        captured = capsys.readouterr()
        assert "Teams directory not found" in captured.out


class TestTeamsShow:
    """Test teams show command."""

    def test_show_team_info(self, temp_test_dirs, capsys):
        """Test showing team information."""
        args = make_args(temp_test_dirs['teams'], name='test_research_team')
        _team_command.handle_show(args, [])

        captured = capsys.readouterr()
        assert "Team: test_research_team" in captured.out
        assert "Test research team for CLI testing" in captured.out
        assert "Leader: test_research_lead" in captured.out
        assert "Team Members (2):" in captured.out
        assert "test_researcher" in captured.out
        assert "test_writer" in captured.out
        assert "Team Constitution:" in captured.out
        assert "Test team constitution" in captured.out
        assert "Inputs (2):" in captured.out
        assert "--topic" in captured.out
        assert "--depth" in captured.out
        assert "Example usage:" in captured.out

    def test_show_team_nonexistent(self, temp_test_dirs):
        """Test showing nonexistent team."""
        args = make_args(temp_test_dirs['teams'], name='nonexistent_team')
        with pytest.raises(SystemExit):
            _team_command.handle_show(args, [])


class TestTeamsExecute:
    """Test teams execute command."""

    @patch('orac.cli.team.Team')
    @patch('orac.cli.team.ToolRegistry')
    def test_execute_team_success(self, mock_registry_class, mock_team_class, temp_test_dirs):
        """Test successful team execution."""
        # Mock the classes and their instances
        mock_registry = Mock()
        mock_registry_class.return_value = mock_registry

        mock_team_instance = Mock()
        mock_team_instance.run.return_value = "Research completed successfully!"
        mock_team_class.return_value = mock_team_instance

        # Create mock args
        args = make_args(
            temp_test_dirs['teams'],
            agents_dir=temp_test_dirs['agents'],
            name='test_research_team'
        )

        remaining_args = ['--topic', 'AI ethics', '--depth', 'comprehensive']

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = captured_output = StringIO()

        try:
            _team_command.handle_run(args, remaining_args)

            output = captured_output.getvalue()
            assert "TEAM RESULT" in output
            assert "Research completed successfully!" in output

            # Verify team was called correctly
            mock_team_instance.run.assert_called_once_with(
                topic='AI ethics',
                depth='comprehensive'
            )

        finally:
            sys.stdout = old_stdout

    def test_execute_team_missing_file(self, temp_test_dirs):
        """Test executing nonexistent team."""
        args = make_args(temp_test_dirs['teams'], name='nonexistent_team')

        with pytest.raises(SystemExit):
            _team_command.handle_run(args, [])

    @patch('orac.cli.team.Team')
    @patch('orac.cli.team.ToolRegistry')
    def test_execute_team_missing_required_arg(self, mock_registry_class, mock_team_class, temp_test_dirs):
        """Test executing team with missing required arguments."""
        args = make_args(
            temp_test_dirs['teams'],
            agents_dir=temp_test_dirs['agents'],
            name='test_research_team'
        )

        # Missing required --topic argument
        remaining_args = ['--depth', 'standard']

        with pytest.raises(SystemExit):
            _team_command.handle_run(args, remaining_args)

    @patch('orac.cli.team.Team')
    @patch('orac.cli.team.ToolRegistry')
    def test_execute_team_with_defaults(self, mock_registry_class, mock_team_class, temp_test_dirs):
        """Test executing team using default values."""
        # Mock the classes and their instances
        mock_registry = Mock()
        mock_registry_class.return_value = mock_registry

        mock_team_instance = Mock()
        mock_team_instance.run.return_value = "Research completed with defaults!"
        mock_team_class.return_value = mock_team_instance

        args = make_args(
            temp_test_dirs['teams'],
            agents_dir=temp_test_dirs['agents'],
            name='test_research_team'
        )

        # Only provide required argument, depth should use default
        remaining_args = ['--topic', 'Quantum computing']

        old_stdout = sys.stdout
        sys.stdout = StringIO()

        try:
            _team_command.handle_run(args, remaining_args)

            # Verify team was called with default depth
            mock_team_instance.run.assert_called_once_with(
                topic='Quantum computing',
                depth='standard'  # default value
            )

        finally:
            sys.stdout = old_stdout


# Mark tests for different categories
pytestmark = pytest.mark.integration
