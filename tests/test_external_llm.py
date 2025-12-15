"""
External LLM integration tests that make real API calls.

These tests require actual API keys and make real calls to external services.
They are marked as 'external' and can be run separately with:
    pytest -m external

API Key Setup:
1. Set GOOGLE_API_KEY (or other provider keys) in environment, OR
2. Create a .env file with your API keys - tests will ask permission to load it, OR  
3. Set ORAC_TEST_AUTO_DOTENV=1 to auto-load .env without prompting

Examples:
    # Run with environment variable
    GOOGLE_API_KEY=your_key pytest -m external
    
    # Run with .env file (will prompt for permission)
    pytest -m external
    
    # Run with auto .env loading
    ORAC_TEST_AUTO_DOTENV=1 pytest -m external
"""

import pytest
import json
import os
import tempfile
from pathlib import Path
import orac
from orac.prompt import Prompt
from orac.config import Provider

# Try to load dotenv if available
try:
    from dotenv import load_dotenv
    _dotenv_available = True
except ImportError:
    _dotenv_available = False


def _ensure_api_key():
    """Ensure API key is available, with permission to load from .env if needed."""
    if os.environ.get("GOOGLE_API_KEY"):
        return True
    
    if not _dotenv_available:
        return False
    
    # Check if .env file exists
    env_file = Path.cwd() / ".env"
    if not env_file.exists():
        return False
    
    # Ask for permission to load .env
    print(f"\nGOOGLE_API_KEY not found in environment.")
    print(f"Found .env file at: {env_file}")
    
    if not os.environ.get("ORAC_TEST_AUTO_DOTENV"):
        response = input("Load API key from .env file for external tests? [y/N]: ")
        if response.lower() not in ("y", "yes"):
            return False
    
    # Load .env and check again
    load_dotenv(env_file)
    return bool(os.environ.get("GOOGLE_API_KEY"))


@pytest.fixture(scope="function")  # Changed from module to function scope
def external_client():
    """Initialize orac with Google provider for external tests."""
    # Ensure we start fresh
    orac.reset()
    
    # Try to ensure API key is available
    if not os.environ.get("GOOGLE_API_KEY"):
        if not _ensure_api_key():
            pytest.skip("GOOGLE_API_KEY not available - external LLM test requires API key")
    
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


@pytest.mark.external
def test_file_upload_integration(external_client):
    """Test file upload functionality - ensures os.path.basename works correctly."""
    # Create a temporary text file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("This is a test document with sample content for analysis.")
        temp_file_path = f.name
    
    try:
        # Create a simple prompt that uses file input
        prompt = Prompt("chat")  # Using basic chat prompt
        
        # Test that file handling doesn't crash with 'os' error
        # The completion will likely fail due to the prompt not being designed for files,
        # but it should not fail with "name 'os' is not defined"
        try:
            result = prompt.completion(
                "Summarize this document", 
                files=[temp_file_path]
            )
            # If it succeeds, great! Check we got some response
            assert result is not None
            assert len(result.strip()) > 0
            
        except Exception as e:
            # Check that the error is NOT the 'os' not defined error
            error_msg = str(e).lower()
            assert "name 'os' is not defined" not in error_msg, f"File handling still has 'os' import issue: {e}"
            
            # Expected errors are fine (API limits, prompt format, etc.)
            # We just want to ensure the file path processing doesn't crash
            print(f"Expected error during file processing (not 'os' error): {e}")
            
    finally:
        # Clean up temp file
        try:
            os.unlink(temp_file_path)
        except FileNotFoundError:
            pass


# Team tests that require external authentication
import shutil
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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