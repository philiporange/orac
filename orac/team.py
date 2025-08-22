"""
Minimal team implementation for Orac.

Teams provide a leader agent orchestrating subagents for collaborative task completion.
A team consists of a leader agent that can delegate tasks to specialist agents,
with optional constitution defining team operating principles.
"""

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional

from orac.agent import Agent, AgentSpec, load_agent_spec
from orac.registry import ToolRegistry, RegisteredTool
from orac.config import Provider
from orac.providers import ProviderRegistry


@dataclass
class TeamSpec:
    """Team specification loaded from YAML."""
    name: str
    description: str
    leader: str
    agents: List[str]
    inputs: List[Dict[str, Any]] = field(default_factory=list)
    outputs: List[Dict[str, Any]] = field(default_factory=list)
    constitution: Optional[str] = None


class Team:
    """Manages a team of agents with a leader orchestrating subagents."""

    def __init__(self, team_spec: TeamSpec, registry: ToolRegistry,
                 agents_dir: str = None):
        self.spec = team_spec
        self.registry = registry
        self.agents_dir = Path(agents_dir or "orac/agents")

        # Load agent specifications
        self.leader_spec = self._load_agent_spec(self.spec.leader)
        self.agent_specs = {
            agent_name: self._load_agent_spec(agent_name)
            for agent_name in self.spec.agents
        }

        # Create team registry with agents as tools
        self.team_registry = self._create_team_registry()

    def _load_agent_spec(self, agent_name: str) -> AgentSpec:
        """Load an agent specification."""
        agent_path = self.agents_dir / f"{agent_name}.yaml"
        return load_agent_spec(agent_path)

    def _create_team_registry(self) -> ToolRegistry:
        """Create registry that includes team agents as delegatable tools."""
        team_registry = ToolRegistry(
            prompts_dir=self.registry.prompts_dir,
            flows_dir=self.registry.flows_dir,
            tools_dir=self.registry.tools_dir
        )

        # Add each team agent as a tool the leader can delegate to
        for agent_name, agent_spec in self.agent_specs.items():
            tool_key = f"agent:{agent_name}"
            team_registry.tools[tool_key] = RegisteredTool(
                name=agent_name,
                type="agent",
                description=agent_spec.description,
                inputs=agent_spec.inputs,
                outputs=[{"name": "result", "type": "string"}],
                file_path=self.agents_dir / f"{agent_name}.yaml"
            )

        # Add delegation tool
        team_registry.tools["tool:delegate"] = RegisteredTool(
            name="delegate",
            type="tool",
            description="Delegate a task to a specific team agent",
            inputs=[
                {"name": "agent", "type": "string", "description": "Name of agent to delegate to"},
                {"name": "task", "type": "string", "description": "Task description"},
                {"name": "inputs", "type": "object", "description": "Input parameters for the agent"}
            ],
            outputs=[{"name": "result", "type": "string"}]
        )

        return team_registry

    def run(self, **kwargs) -> str:
        """Execute the team to accomplish a goal."""
        # Create leader agent with team capabilities
        leader_agent = TeamLeaderAgent(
            agent_spec=self.leader_spec,
            tool_registry=self.team_registry,
            team_members=self.agent_specs,
            constitution=self.spec.constitution,
            agents_dir=self.agents_dir
        )

        return leader_agent.run(**kwargs)


class TeamLeaderAgent(Agent):
    """Leader agent with delegation capabilities."""

    def __init__(self, agent_spec: AgentSpec, tool_registry: ToolRegistry,
                 team_members: Dict[str, AgentSpec] = None,
                 constitution: Optional[str] = None,
                 agents_dir: Path = None):
        # Setup provider for the leader agent
        from .providers import ProviderRegistry
        leader_provider_registry = ProviderRegistry()
        provider_str = agent_spec.provider or "google"
        provider = Provider(provider_str)
        
        leader_provider_registry.add_provider(
            provider,
            allow_env=True,
            interactive=False
        )
        
        super().__init__(agent_spec, tool_registry, leader_provider_registry, provider)
        self.team_members = team_members or {}
        self.constitution = constitution
        self.agents_dir = agents_dir

    def _execute_tool(self, tool_name: str, tool_inputs: Dict[str, Any]) -> str:
        """Override to handle team delegation."""
        if tool_name == "tool:delegate":
            return self._delegate_task(
                tool_inputs["agent"],
                tool_inputs["task"],
                tool_inputs.get("inputs", {})
            )
        elif tool_name.startswith("agent:"):
            # Direct agent execution
            agent_name = tool_name.split(":")[1]
            return self._execute_agent(agent_name, tool_inputs)
        else:
            # Delegate to parent class for standard tools
            return super()._execute_tool(tool_name, tool_inputs)

    def _delegate_task(self, agent_name: str, task: str, inputs: Dict[str, Any]) -> str:
        """Delegate a task to a specific agent."""
        if agent_name not in self.team_members:
            return f"Error: Agent '{agent_name}' not found in team"

        # Create agent instance with its own provider setup
        agent_spec = self.team_members[agent_name]
        
        # Setup provider for this agent
        from .providers import ProviderRegistry
        agent_provider_registry = ProviderRegistry()
        provider_str = agent_spec.provider or "google"
        provider = Provider(provider_str)
        
        agent_provider_registry.add_provider(
            provider,
            allow_env=True,
            interactive=False  # Non-interactive for delegation
        )
        
        agent = Agent(
            agent_spec=agent_spec,
            tool_registry=self.registry,
            provider_registry=agent_provider_registry,
            provider=provider
        )

        # Execute with task and inputs
        all_inputs = {"task": task, **inputs}
        return agent.run(**all_inputs)

    def _execute_agent(self, agent_name: str, inputs: Dict[str, Any]) -> str:
        """Execute a specific agent with given inputs."""
        if agent_name not in self.team_members:
            return f"Error: Agent '{agent_name}' not found in team"

        # Create agent instance with its own provider setup
        agent_spec = self.team_members[agent_name]
        
        # Setup provider for this agent
        from .providers import ProviderRegistry
        agent_provider_registry = ProviderRegistry()
        provider_str = agent_spec.provider or "google"
        provider = Provider(provider_str)
        
        agent_provider_registry.add_provider(
            provider,
            allow_env=True,
            interactive=False  # Non-interactive for delegation
        )
        
        agent = Agent(
            agent_spec=agent_spec,
            tool_registry=self.registry,
            provider_registry=agent_provider_registry,
            provider=provider
        )

        return agent.run(**inputs)


def load_team_spec(team_path: Path) -> TeamSpec:
    """Load team specification from YAML."""
    with open(team_path, 'r') as f:
        data = yaml.safe_load(f)
    return TeamSpec(**data)