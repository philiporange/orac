"""Tests for agent-as-tool: registry discovery, spec formatting, and dispatch.

Verifies that the ToolRegistry discovers agent YAML files, formats their specs
correctly, and that Agent._execute_agent_tool dispatches to sub-agents.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from orac.registry import ToolRegistry, RegisteredTool
from orac.agent import Agent, AgentSpec, load_agent_spec


@pytest.fixture
def agent_dir(tmp_path):
    """Create a temp directory with a sample agent YAML."""
    agents = tmp_path / "agents"
    agents.mkdir()
    (agents / "test_agent.yaml").write_text(
        "name: test_agent\n"
        "description: A test sub-agent\n"
        "system_prompt: You are a test agent. $${tool_list}\n"
        "inputs:\n"
        "  - name: query\n"
        "    type: string\n"
        "    description: The query\n"
        "tools:\n"
        "  - tool:finish\n"
        "model_name: gemini-2.5-flash\n"
        "max_iterations: 3\n"
    )
    return agents


@pytest.fixture
def empty_dirs(tmp_path):
    """Create empty directories for prompts/flows/tools/teams."""
    for name in ["prompts", "flows", "tools", "teams"]:
        (tmp_path / name).mkdir()
    return tmp_path


# ── Registry discovery ─────────────────────────────────────────────


class TestRegistryAgentDiscovery:
    def test_discovers_agent_yaml(self, agent_dir, empty_dirs):
        registry = ToolRegistry(
            prompts_dir=str(empty_dirs / "prompts"),
            flows_dir=str(empty_dirs / "flows"),
            tools_dir=str(empty_dirs / "tools"),
            teams_dir=str(empty_dirs / "teams"),
            agents_dir=str(agent_dir),
        )
        tool = registry.get_tool("agent:test_agent")
        assert tool is not None
        assert tool.type == "agent"
        assert tool.name == "test_agent"
        assert "test sub-agent" in tool.description

    def test_agent_has_inputs(self, agent_dir, empty_dirs):
        registry = ToolRegistry(
            prompts_dir=str(empty_dirs / "prompts"),
            flows_dir=str(empty_dirs / "flows"),
            tools_dir=str(empty_dirs / "tools"),
            teams_dir=str(empty_dirs / "teams"),
            agents_dir=str(agent_dir),
        )
        tool = registry.get_tool("agent:test_agent")
        assert len(tool.inputs) == 1
        assert tool.inputs[0]["name"] == "query"

    def test_empty_agents_dir(self, empty_dirs):
        agents_dir = empty_dirs / "agents_empty"
        agents_dir.mkdir()
        registry = ToolRegistry(
            prompts_dir=str(empty_dirs / "prompts"),
            flows_dir=str(empty_dirs / "flows"),
            tools_dir=str(empty_dirs / "tools"),
            teams_dir=str(empty_dirs / "teams"),
            agents_dir=str(agents_dir),
        )
        # No agent tools registered
        agent_tools = [k for k in registry.tools if k.startswith("agent:")]
        assert len(agent_tools) == 0

    def test_nonexistent_agents_dir(self, empty_dirs):
        registry = ToolRegistry(
            prompts_dir=str(empty_dirs / "prompts"),
            flows_dir=str(empty_dirs / "flows"),
            tools_dir=str(empty_dirs / "tools"),
            teams_dir=str(empty_dirs / "teams"),
            agents_dir=str(empty_dirs / "no_such_dir"),
        )
        agent_tools = [k for k in registry.tools if k.startswith("agent:")]
        assert len(agent_tools) == 0


# ── get_tools_spec formatting ──────────────────────────────────────


class TestAgentToolSpec:
    def test_formats_agent_spec(self, agent_dir, empty_dirs):
        registry = ToolRegistry(
            prompts_dir=str(empty_dirs / "prompts"),
            flows_dir=str(empty_dirs / "flows"),
            tools_dir=str(empty_dirs / "tools"),
            teams_dir=str(empty_dirs / "teams"),
            agents_dir=str(agent_dir),
        )
        spec_text = registry.get_tools_spec(["agent:test_agent"])
        assert "agent:test_agent" in spec_text
        assert "test sub-agent" in spec_text
        assert "query" in spec_text


# ── load_agent_spec ────────────────────────────────────────────────


class TestLoadAgentSpec:
    def test_loads_from_path(self, agent_dir):
        spec = load_agent_spec(agent_dir / "test_agent.yaml")
        assert spec.name == "test_agent"
        assert spec.max_iterations == 3
        assert spec.model_name == "gemini-2.5-flash"

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_agent_spec("/nonexistent/agent.yaml")


# ── _execute_agent_tool ────────────────────────────────────────────


class TestExecuteAgentTool:
    @patch("orac.agent.load_agent_spec")
    @patch("orac.agent.ProviderRegistry")
    @patch("orac.agent.Agent")
    def test_dispatches_to_sub_agent(self, MockAgent, MockProviderReg, mock_load_spec):
        """Verify _execute_agent_tool creates a sub-agent and calls run()."""
        mock_load_spec.return_value = AgentSpec(
            name="sub",
            description="sub agent",
            system_prompt="test",
            provider="google",
        )
        mock_sub_agent = MagicMock()
        mock_sub_agent.run.return_value = "sub-agent result"
        MockAgent.return_value = mock_sub_agent

        # Create the parent agent
        parent_spec = AgentSpec(
            name="parent",
            description="parent agent",
            system_prompt="test",
        )
        parent = Agent.__new__(Agent)
        parent.spec = parent_spec
        parent.registry = MagicMock()
        parent.registry.prompts_dir = Path("/tmp/prompts")
        parent.registry.flows_dir = Path("/tmp/flows")
        parent.registry.tools_dir = Path("/tmp/tools")
        parent.provider_registry = MagicMock()
        parent.provider = MagicMock()
        parent.provider.value = "google"

        tool = RegisteredTool(
            name="sub",
            type="agent",
            description="sub agent",
            file_path=Path("/tmp/agents/sub.yaml"),
        )

        result = parent._execute_agent_tool(tool, {"query": "test"})
        assert result == "sub-agent result"
        mock_sub_agent.run.assert_called_once_with(query="test")
