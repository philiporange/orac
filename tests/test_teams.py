"""Tests for teams functionality."""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import Mock, patch

from orac.team import Team, TeamSpec, TeamLeaderAgent, load_team_spec
from orac.agent import AgentSpec
from orac.registry import ToolRegistry
from orac.config import Provider, Config
from orac.providers import ProviderRegistry


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
def sample_team_spec():
    """Create a sample team specification."""
    return TeamSpec(
        name="test_team",
        description="Test team for unit tests",
        leader="test_leader",
        agents=["agent1", "agent2"],
        inputs=[
            {"name": "topic", "type": "string", "required": True},
            {"name": "depth", "type": "string", "default": "standard"}
        ],
        outputs=[
            {"name": "result", "type": "string"}
        ],
        constitution="Test team rules"
    )


@pytest.fixture
def sample_agents(temp_dirs):
    """Create sample agent files."""
    agents_dir = Path(temp_dirs['agents'])
    
    # Leader agent
    leader_spec = {
        'name': 'Test Leader',
        'description': 'Test leader agent',
        'system_prompt': 'You are a test leader',
        'inputs': [
            {'name': 'topic', 'type': 'string', 'required': True}
        ],
        'tools': ['agent:agent1', 'agent:agent2', 'tool:delegate', 'tool:finish'],
        'max_iterations': 10
    }
    
    with open(agents_dir / "test_leader.yaml", 'w') as f:
        import yaml
        yaml.dump(leader_spec, f)
    
    # Agent 1
    agent1_spec = {
        'name': 'Agent 1',
        'description': 'First test agent',
        'system_prompt': 'You are agent 1',
        'inputs': [
            {'name': 'task', 'type': 'string', 'required': True}
        ],
        'tools': ['tool:finish'],
        'max_iterations': 5
    }
    
    with open(agents_dir / "agent1.yaml", 'w') as f:
        yaml.dump(agent1_spec, f)
    
    # Agent 2
    agent2_spec = {
        'name': 'Agent 2', 
        'description': 'Second test agent',
        'system_prompt': 'You are agent 2',
        'inputs': [
            {'name': 'task', 'type': 'string', 'required': True}
        ],
        'tools': ['tool:finish'],
        'max_iterations': 5
    }
    
    with open(agents_dir / "agent2.yaml", 'w') as f:
        yaml.dump(agent2_spec, f)


class TestTeamSpec:
    """Test TeamSpec dataclass."""
    
    def test_team_spec_creation(self):
        """Test TeamSpec can be created with required fields."""
        spec = TeamSpec(
            name="test",
            description="Test team",
            leader="leader",
            agents=["agent1", "agent2"]
        )
        
        assert spec.name == "test"
        assert spec.description == "Test team"
        assert spec.leader == "leader"
        assert spec.agents == ["agent1", "agent2"]
        assert spec.inputs == []
        assert spec.outputs == []
        assert spec.constitution is None
    
    def test_team_spec_with_optional_fields(self):
        """Test TeamSpec with all optional fields."""
        inputs = [{"name": "topic", "type": "string"}]
        outputs = [{"name": "result", "type": "string"}]
        constitution = "Team rules"
        
        spec = TeamSpec(
            name="test",
            description="Test team",
            leader="leader", 
            agents=["agent1"],
            inputs=inputs,
            outputs=outputs,
            constitution=constitution
        )
        
        assert spec.inputs == inputs
        assert spec.outputs == outputs
        assert spec.constitution == constitution


class TestTeam:
    """Test Team class functionality."""
    
    def test_team_initialization(self, sample_team_spec, sample_agents, temp_dirs):
        """Test Team can be initialized properly."""
        registry = ToolRegistry()
        provider_registry = ProviderRegistry()
        provider = Provider.OPENROUTER
        
        team = Team(
            team_spec=sample_team_spec,
            registry=registry,
            provider_registry=provider_registry,
            provider=provider,
            agents_dir=temp_dirs['agents']
        )
        
        assert team.spec == sample_team_spec
        assert team.registry == registry
        assert team.provider == provider
        assert team.agents_dir == Path(temp_dirs['agents'])
    
    def test_load_agent_spec(self, sample_team_spec, sample_agents, temp_dirs):
        """Test loading agent specifications."""
        registry = ToolRegistry()
        provider_registry = ProviderRegistry()
        provider = Provider.OPENROUTER
        
        team = Team(
            team_spec=sample_team_spec,
            registry=registry,
            provider_registry=provider_registry,
            provider=provider,
            agents_dir=temp_dirs['agents']
        )
        
        # Test loading leader spec
        leader_spec = team.leader_spec
        assert leader_spec.name == "Test Leader"
        assert leader_spec.description == "Test leader agent"
        
        # Test loading agent specs
        assert "agent1" in team.agent_specs
        assert "agent2" in team.agent_specs
        assert team.agent_specs["agent1"].name == "Agent 1"
        assert team.agent_specs["agent2"].name == "Agent 2"
    
    def test_create_team_registry(self, sample_team_spec, sample_agents, temp_dirs):
        """Test creation of team registry with agent tools."""
        registry = ToolRegistry()
        provider_registry = ProviderRegistry()
        provider = Provider.OPENROUTER
        
        team = Team(
            team_spec=sample_team_spec,
            registry=registry,
            provider_registry=provider_registry,
            provider=provider,
            agents_dir=temp_dirs['agents']
        )
        
        # Test that agents are registered as tools
        assert "agent:agent1" in team.team_registry.tools
        assert "agent:agent2" in team.team_registry.tools
        assert "tool:delegate" in team.team_registry.tools
        
        # Test agent tool properties
        agent1_tool = team.team_registry.tools["agent:agent1"]
        assert agent1_tool.name == "agent1"
        assert agent1_tool.type == "agent"
        assert agent1_tool.description == "First test agent"
        
        # Test delegate tool properties
        delegate_tool = team.team_registry.tools["tool:delegate"]
        assert delegate_tool.name == "delegate"
        assert delegate_tool.type == "tool"
        assert len(delegate_tool.inputs) == 3  # agent, task, inputs


class TestTeamLeaderAgent:
    """Test TeamLeaderAgent functionality."""
    
    @pytest.fixture
    def mock_agent_spec(self):
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
    def mock_team_members(self):
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
    
    def test_team_leader_initialization(self, mock_agent_spec, mock_team_members):
        """Test TeamLeaderAgent initialization."""
        registry = ToolRegistry()
        provider_registry = ProviderRegistry()
        provider = Provider.OPENROUTER
        constitution = "Test rules"
        
        leader = TeamLeaderAgent(
            agent_spec=mock_agent_spec,
            tool_registry=registry,
            provider_registry=provider_registry,
            provider=provider,
            team_members=mock_team_members,
            constitution=constitution
        )
        
        assert leader.team_members == mock_team_members
        assert leader.constitution == constitution
    
    @patch('orac.team.Agent')
    def test_delegate_task(self, mock_agent_class, mock_agent_spec, mock_team_members):
        """Test task delegation functionality."""
        registry = ToolRegistry()
        provider_registry = ProviderRegistry()
        provider = Provider.OPENROUTER
        
        # Mock agent instance and return value
        mock_agent_instance = Mock()
        mock_agent_instance.run.return_value = "Task completed"
        mock_agent_class.return_value = mock_agent_instance
        
        leader = TeamLeaderAgent(
            agent_spec=mock_agent_spec,
            tool_registry=registry,
            provider_registry=provider_registry,
            provider=provider,
            team_members=mock_team_members
        )
        
        # Test successful delegation
        result = leader._delegate_task("agent1", "Test task", {"param": "value"})
        
        assert result == "Task completed"
        mock_agent_class.assert_called_once()
        mock_agent_instance.run.assert_called_once_with(
            task="Test task", param="value"
        )
    
    def test_delegate_task_unknown_agent(self, mock_agent_spec, mock_team_members):
        """Test delegation to unknown agent."""
        registry = ToolRegistry()
        provider_registry = ProviderRegistry()
        provider = Provider.OPENROUTER
        
        leader = TeamLeaderAgent(
            agent_spec=mock_agent_spec,
            tool_registry=registry,
            provider_registry=provider_registry,
            provider=provider,
            team_members=mock_team_members
        )
        
        result = leader._delegate_task("unknown_agent", "Test task", {})
        assert "Error: Agent 'unknown_agent' not found in team" in result
    
    @patch('orac.team.Agent')
    def test_execute_agent_direct(self, mock_agent_class, mock_agent_spec, mock_team_members):
        """Test direct agent execution."""
        registry = ToolRegistry()
        provider_registry = ProviderRegistry()
        provider = Provider.OPENROUTER
        
        # Mock agent instance and return value
        mock_agent_instance = Mock()
        mock_agent_instance.run.return_value = "Agent result"
        mock_agent_class.return_value = mock_agent_instance
        
        leader = TeamLeaderAgent(
            agent_spec=mock_agent_spec,
            tool_registry=registry,
            provider_registry=provider_registry,
            provider=provider,
            team_members=mock_team_members
        )
        
        # Test direct agent execution
        result = leader._execute_agent("agent1", {"param": "value"})
        
        assert result == "Agent result"
        mock_agent_instance.run.assert_called_once_with(param="value")


class TestLoadTeamSpec:
    """Test loading team specifications from YAML."""
    
    def test_load_team_spec(self, temp_dirs):
        """Test loading team spec from YAML file."""
        teams_dir = Path(temp_dirs['teams'])
        
        # Create test team YAML
        team_data = {
            'name': 'test_team',
            'description': 'Test team description',
            'leader': 'test_leader',
            'agents': ['agent1', 'agent2'],
            'inputs': [
                {'name': 'topic', 'type': 'string', 'required': True}
            ],
            'constitution': 'Test rules'
        }
        
        team_file = teams_dir / "test_team.yaml"
        with open(team_file, 'w') as f:
            import yaml
            yaml.dump(team_data, f)
        
        # Load the spec
        spec = load_team_spec(team_file)
        
        assert spec.name == 'test_team'
        assert spec.description == 'Test team description'
        assert spec.leader == 'test_leader'
        assert spec.agents == ['agent1', 'agent2']
        assert len(spec.inputs) == 1
        assert spec.inputs[0]['name'] == 'topic'
        assert spec.constitution == 'Test rules'


class TestTeamIntegration:
    """Integration tests for complete team functionality."""
    
    @patch('orac.team.TeamLeaderAgent')
    def test_team_run(self, mock_leader_class, sample_team_spec, sample_agents, temp_dirs):
        """Test complete team execution."""
        registry = ToolRegistry()
        provider_registry = ProviderRegistry()
        provider = Provider.OPENROUTER
        
        # Mock leader instance and return value
        mock_leader_instance = Mock()
        mock_leader_instance.run.return_value = "Team task completed"
        mock_leader_class.return_value = mock_leader_instance
        
        team = Team(
            team_spec=sample_team_spec,
            registry=registry,
            provider_registry=provider_registry,
            provider=provider,
            agents_dir=temp_dirs['agents']
        )
        
        # Test team execution
        result = team.run(topic="test topic", depth="comprehensive")
        
        assert result == "Team task completed"
        mock_leader_class.assert_called_once()
        mock_leader_instance.run.assert_called_once_with(
            topic="test topic", depth="comprehensive"
        )


# Mark tests requiring external services
pytestmark = pytest.mark.unit