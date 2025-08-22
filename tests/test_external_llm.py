"""
External LLM integration tests that make real API calls.

These tests require actual API keys and make real calls to external services.
They are marked as 'external' and can be run separately with:
    pytest -m external

Set GOOGLE_API_KEY or other provider keys to run these tests.
"""

import pytest
import json
import os
import orac
from orac.prompt import Prompt
from orac.config import Provider


@pytest.fixture(scope="module")
def external_client():
    """Initialize orac with Google provider for external tests."""
    # Initialize orac with Google provider using environment API key
    orac.init(
        default_provider=Provider.GOOGLE,
        providers={
            Provider.GOOGLE: {"api_key_env": "GOOGLE_API_KEY"}
        },
        interactive=False
    )
    yield
    # Clean up
    orac.reset()


@pytest.mark.external
@pytest.mark.skipif(
    not os.environ.get("GOOGLE_API_KEY"), 
    reason="GOOGLE_API_KEY not set - external LLM test requires API key"
)
def test_recipe_prompt_external(external_client):
    """Test recipe prompt with external Google API call."""
    # Create prompt instance - provider already set by external_client
    recipe = Prompt("recipe")
    
    # Make real API call
    result = recipe.completion(dish="chocolate chip cookies")
    
    # Verify response structure and content
    assert result is not None
    assert len(result.strip()) > 0
    
    # Since recipe prompt returns JSON, parse and verify structure
    try:
        recipe_data = json.loads(result)
        assert isinstance(recipe_data, dict)
        assert "title" in recipe_data
        assert "ingredients" in recipe_data
        assert "steps" in recipe_data
        assert isinstance(recipe_data["ingredients"], list)
        assert isinstance(recipe_data["steps"], list)
        assert len(recipe_data["ingredients"]) > 0
        assert len(recipe_data["steps"]) > 0
        
        # Verify content mentions cookies
        title_lower = recipe_data["title"].lower()
        assert "cookie" in title_lower or "chocolate" in title_lower
        
    except json.JSONDecodeError:
        pytest.fail(f"Recipe prompt should return valid JSON, got: {result}")


@pytest.mark.external
@pytest.mark.skipif(
    not os.environ.get("GOOGLE_API_KEY"), 
    reason="GOOGLE_API_KEY not set - external LLM test requires API key"
)
def test_recipe_prompt_callable_interface(external_client):
    """Test recipe prompt using callable interface with external API."""
    recipe = Prompt("recipe")
    
    # Use callable interface
    result = recipe(dish="banana bread")
    
    # Should auto-detect JSON and return dict
    assert isinstance(result, dict)
    assert "title" in result
    assert "ingredients" in result
    assert "steps" in result
    
    # Check content is relevant
    title_lower = result["title"].lower()
    assert "banana" in title_lower or "bread" in title_lower


# Team tests that require external authentication
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch
from orac.team import Team, TeamSpec, TeamLeaderAgent
from orac.agent import AgentSpec
from orac.registry import ToolRegistry


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing."""
    base_temp = tempfile.mkdtemp()
    teams_dir = Path(base_temp) / "teams"
    agents_dir = Path(base_temp) / "agents"
    teams_dir.mkdir()
    agents_dir.mkdir()
    
    yield {
        'base': base_temp,
        'teams': str(teams_dir),
        'agents': str(agents_dir)
    }
    
    shutil.rmtree(base_temp)


@pytest.fixture
def mock_agent_spec():
    """Mock agent specification."""
    return AgentSpec(
        name="Test Leader",
        description="Test leader",
        system_prompt="Test prompt",
        inputs=[{"name": "topic", "type": "string"}],
        tools=["tool:delegate", "tool:finish"],
        max_iterations=10
    )


@pytest.fixture
def mock_team_members():
    """Mock team member specs."""
    return {
        "agent1": AgentSpec(
            name="Agent 1",
            description="First agent",
            system_prompt="Agent 1 prompt",
            inputs=[{"name": "task", "type": "string"}],
            tools=["tool:finish"],
            max_iterations=5
        ),
        "agent2": AgentSpec(
            name="Agent 2", 
            description="Second agent",
            system_prompt="Agent 2 prompt",
            inputs=[{"name": "task", "type": "string"}],
            tools=["tool:finish"],
            max_iterations=5
        )
    }


@pytest.mark.external
@pytest.mark.skipif(
    not os.environ.get("GOOGLE_API_KEY"), 
    reason="GOOGLE_API_KEY not set - external team test requires API key"
)
def test_team_leader_initialization(mock_agent_spec, mock_team_members):
    """Test TeamLeaderAgent initialization."""
    registry = ToolRegistry()
    constitution = "Test rules"
    
    leader = TeamLeaderAgent(
        agent_spec=mock_agent_spec,
        tool_registry=registry,
        team_members=mock_team_members,
        constitution=constitution
    )
    
    assert leader.team_members == mock_team_members
    assert leader.constitution == constitution


@pytest.mark.external
@pytest.mark.skipif(
    not os.environ.get("GOOGLE_API_KEY"), 
    reason="GOOGLE_API_KEY not set - external team test requires API key"
)
@patch('orac.team.Agent')
def test_delegate_task(mock_agent_class, mock_agent_spec, mock_team_members):
    """Test task delegation functionality."""
    registry = ToolRegistry()
    
    # Mock agent instance and return value
    mock_agent_instance = Mock()
    mock_agent_instance.run.return_value = "Task completed"
    mock_agent_class.return_value = mock_agent_instance
    
    leader = TeamLeaderAgent(
        agent_spec=mock_agent_spec,
        tool_registry=registry,
        team_members=mock_team_members
    )
    
    # Test successful delegation
    result = leader._delegate_task("agent1", "Test task", {"param": "value"})
    
    assert result == "Task completed"
    mock_agent_class.assert_called_once()
    mock_agent_instance.run.assert_called_once_with(
        task="Test task", param="value"
    )


@pytest.mark.external
@pytest.mark.skipif(
    not os.environ.get("GOOGLE_API_KEY"), 
    reason="GOOGLE_API_KEY not set - external team test requires API key"
)
def test_delegate_task_unknown_agent(mock_agent_spec, mock_team_members):
    """Test delegation to unknown agent."""
    registry = ToolRegistry()
    
    leader = TeamLeaderAgent(
        agent_spec=mock_agent_spec,
        tool_registry=registry,
        team_members=mock_team_members
    )
    
    result = leader._delegate_task("unknown_agent", "Test task", {})
    assert "Error: Agent 'unknown_agent' not found in team" in result


@pytest.mark.external
@pytest.mark.skipif(
    not os.environ.get("GOOGLE_API_KEY"), 
    reason="GOOGLE_API_KEY not set - external team test requires API key"
)
@patch('orac.team.Agent')
def test_execute_agent_direct(mock_agent_class, mock_agent_spec, mock_team_members):
    """Test direct agent execution."""
    registry = ToolRegistry()
    
    # Mock agent instance and return value
    mock_agent_instance = Mock()
    mock_agent_instance.run.return_value = "Agent result"
    mock_agent_class.return_value = mock_agent_instance
    
    leader = TeamLeaderAgent(
        agent_spec=mock_agent_spec,
        tool_registry=registry,
        team_members=mock_team_members
    )
    
    # Test direct agent execution
    result = leader._execute_agent("agent1", {"param": "value"})
    
    assert result == "Agent result"
    mock_agent_instance.run.assert_called_once_with(param="value")