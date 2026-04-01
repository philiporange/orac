"""
Agent engine for Orac - enables autonomous ReAct-style agents with tool usage.

Agents use a ReAct (Reason + Act) loop: each iteration queries the LLM for a
JSON action containing thought/tool/inputs, executes the tool, and feeds the
observation back as context. History is automatically compacted when it grows
large or after an idle gap, replacing older messages with an LLM-generated
summary while preserving recent messages for prefix-cache friendliness.

Agents can specify custom API configuration in their YAML:
- provider: The LLM provider to use (e.g., 'openai', 'google')
- base_url: Custom API endpoint URL (optional, overrides provider defaults)
- api_key: API key for authentication (optional, can use environment variables)
- model_name: The model to use for agent reasoning
- tools: List of available tools (prompts, flows, skills)
- compact_after_messages: Message count before compaction triggers (default 12)
- compact_keep_recent: Recent messages to preserve during compaction (default 4)
- summarization_model: Model for summarization (default: agent's own model)
- compact_time_gap_seconds: Idle seconds before time-triggered compaction (default 300)

Note: Command-line flags and programmatic parameters override YAML values.
"""

import re
import yaml
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from string import Template

from .config import Config, Provider
from .registry import ToolRegistry, RegisteredTool
from .openai_client import call_api, Usage, CompletionResult
from .providers import ProviderRegistry
from .prompt import Prompt, _inject_response_format
from .flow import Flow, load_flow
from .skill import Skill, load_skill
from .compaction import maybe_compact
from .logger import logger

@dataclass
class AgentSpec:
    name: str
    description: str
    system_prompt: str
    inputs: List[Dict[str, Any]] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    model_name: str = "gemini-2.5-pro"
    provider: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    generation_config: Dict[str, Any] = field(default_factory=dict)
    max_iterations: int = 15
    compact_after_messages: int = 12
    compact_keep_recent: int = 4
    summarization_model: Optional[str] = None
    compact_time_gap_seconds: int = 300

class Agent:
    def __init__(self, agent_spec: AgentSpec, tool_registry: ToolRegistry, provider_registry: ProviderRegistry, provider: Optional[Provider] = None):
        self.spec = agent_spec
        self.registry = tool_registry
        self.provider_registry = provider_registry
        self.provider = provider
        self.message_history: List[Dict[str, str]] = []
        self.total_usage: Optional[Usage] = None
        self.last_message_time: Optional[datetime] = None

    def _append_message(self, role: str, text: str, pinned: bool = False):
        """Append a message to history and update the last-message timestamp."""
        msg = {"role": role, "text": text}
        if pinned:
            msg["pinned"] = True
        self.message_history.append(msg)
        self.last_message_time = datetime.now()

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Parse JSON from LLM response, stripping markdown code fences if present."""
        stripped = text.strip()
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", stripped, re.DOTALL)
        if match:
            stripped = match.group(1).strip()
        return json.loads(stripped)

    def run(self, include_usage: bool = False, **kwargs) -> str | CompletionResult:
        """Executes the agent's ReAct loop to achieve its goal."""
        
        # 1. Format the initial system prompt with inputs and tool list
        tool_specs = self.registry.get_tools_spec(self.spec.tools)
        
        # Build template vars: kwargs override defaults
        template_vars = {"tool_list": tool_specs, "history": ""}
        template_vars.update(kwargs)
        initial_prompt_template = Template(self.spec.system_prompt)
        system_prompt = initial_prompt_template.safe_substitute(**template_vars)
        
        # Add an initial user message to start the conversation with the provided parameters
        input_summary = ", ".join([f"{k}={v}" for k, v in kwargs.items()])
        self._append_message('user', f"Please help me with the following inputs: {input_summary}")
        
        # If base_url or api_key is specified in spec, log configuration
        if (self.spec.base_url or self.spec.api_key) and self.provider:
            provider_info = self.provider_registry.get_provider_info(self.provider)
            if self.spec.base_url and (not provider_info or provider_info.get('base_url') != self.spec.base_url):
                logger.info(f"Agent will use custom base_url: {self.spec.base_url}")
            if self.spec.api_key:
                logger.info(f"Agent will use custom api_key from YAML")

        for i in range(self.spec.max_iterations):
            print(f"\n--- Iteration {i+1}/{self.spec.max_iterations} ---")

            # Update provider with custom base_url/api_key if specified
            if (self.spec.base_url or self.spec.api_key) and self.provider and i == 0:
                # Only update on first iteration to avoid redundant updates
                provider_info = self.provider_registry.get_provider_info(self.provider)
                needs_update = (
                    not provider_info or
                    (self.spec.base_url and provider_info.get('base_url') != self.spec.base_url)
                )
                if needs_update or self.spec.api_key:
                    try:
                        # Get existing client config to extract API key
                        from .client import Client
                        # Note: We need access to the Client to update provider, but we only have provider_registry
                        # For now, we'll log a warning - full support requires passing Client to Agent
                        custom_items = []
                        if self.spec.base_url:
                            custom_items.append(f"base_url ({self.spec.base_url})")
                        if self.spec.api_key:
                            custom_items.append("api_key")

                        logger.warning(
                            f"Custom {' and '.join(custom_items)} specified in agent YAML but "
                            f"provider update from agent is not yet fully supported. "
                            f"Please configure these when initializing the client."
                        )
                    except Exception as e:
                        logger.warning(f"Could not update provider configuration: {e}")

            # 2. Compact history if needed (before sending to LLM)
            maybe_compact(
                message_history=self.message_history,
                provider_registry=self.provider_registry,
                provider=self.provider,
                model_name=self.spec.summarization_model or self.spec.model_name,
                compact_after_messages=self.spec.compact_after_messages,
                compact_keep_recent=self.spec.compact_keep_recent,
                last_message_time=self.last_message_time,
                compact_time_gap_seconds=self.spec.compact_time_gap_seconds,
            )

            # 3. Query the LLM for the next action
            try:
                # Convert response_mime_type to response_format for OpenAI compatibility
                processed_config = _inject_response_format(self.spec.generation_config)
                completion_result = call_api(
                    provider_registry=self.provider_registry,
                    provider=self.provider,
                    message_history=self.message_history,
                    system_prompt=system_prompt,
                    model_name=self.spec.model_name,
                    generation_config=processed_config
                )
                # Accumulate usage
                if completion_result.usage:
                    self.total_usage = (
                        (self.total_usage + completion_result.usage)
                        if self.total_usage
                        else completion_result.usage
                    )
                response_str = completion_result.text
                action_data = self._extract_json(response_str)
            except Exception as e:
                print(f"ERROR: Failed to get valid action from LLM: {e}")
                self._append_message('user', f"Observation: Invalid action response. Error: {e}")
                continue
            
            thought = action_data.get("thought", "No thought provided.")
            tool_name = action_data.get("tool")
            tool_inputs = action_data.get("inputs", {})
            pin_observation = action_data.get("pin", False)

            print(f"🤔 Thought: {thought}")
            self._append_message('model', json.dumps(action_data, indent=2))

            if not tool_name:
                print("ERROR: LLM did not provide a tool name.")
                self._append_message('user', "Observation: No tool was selected. You must select a tool.")
                continue

            # 4. Handle the 'finish' action
            if tool_name == "tool:finish":
                final_answer = tool_inputs.get("result", "Agent finished without a final answer.")
                print(f"✅ Agent Finished: {final_answer}")
                if include_usage:
                    return CompletionResult(text=final_answer, usage=self.total_usage)
                return final_answer
            
            # 5. Execute the chosen tool
            print(f"🎬 Action: {tool_name} with inputs: {tool_inputs}")
            observation = self._execute_tool(tool_name, tool_inputs)
            
            # 6. Add observation to history and repeat
            print(f"👀 Observation: {observation}")
            self._append_message('user', f"Observation: {str(observation)}",
                                 pinned=bool(pin_observation))
            
        final_message = "Agent stopped: Maximum iterations reached."
        print(final_message)
        if include_usage:
            return CompletionResult(text=final_message, usage=self.total_usage)
        return final_message

    def _execute_tool(self, tool_name: str, tool_inputs: Dict[str, Any]) -> str:
        """Execute a tool and return the observation."""
        tool = self.registry.get_tool(tool_name)
        if not tool:
            return f"Error: Tool '{tool_name}' not found."

        try:
            if tool.type == "prompt":
                # Extract file_path for file attachment support (e.g. transcribe_file)
                file_path = tool_inputs.pop("file_path", None)
                files = [file_path] if file_path else None
                prompt_instance = Prompt(
                    tool.name,
                    prompts_dir=self.registry.prompts_dir,
                    provider=self.provider.value if self.provider else None,
                    files=files,
                )
                return prompt_instance.completion(**tool_inputs)
            elif tool.type == "flow":
                flow_spec = load_flow(tool.file_path)
                flow_engine = Flow(flow_spec)
                return flow_engine.execute(tool_inputs)
            elif tool.type == "tool":
                skill_spec = load_skill(tool.file_path)
                skills_dir = str(tool.file_path.parent) if tool.file_path else None
                skill_engine = Skill(skill_spec, skills_dir=skills_dir)
                return skill_engine.execute(tool_inputs)
            elif tool.type == "agent":
                return self._execute_agent_tool(tool, tool_inputs)
            else:
                return f"Error: Unknown tool type '{tool.type}'"
        except Exception as e:
            return f"Error executing tool '{tool_name}': {e}"

    def _execute_agent_tool(self, tool: RegisteredTool, inputs: Dict[str, Any]) -> str:
        """Execute an agent as a tool, returning its final result."""
        agent_spec = load_agent_spec(tool.file_path)

        agent_provider_registry = ProviderRegistry()
        provider_str = agent_spec.provider or (self.provider.value if self.provider else "google")
        provider = Provider(provider_str)
        agent_provider_registry.add_provider(
            provider, allow_env=True, interactive=False,
        )

        sub_registry = ToolRegistry(
            prompts_dir=str(self.registry.prompts_dir),
            flows_dir=str(self.registry.flows_dir),
            tools_dir=str(self.registry.tools_dir),
        )

        agent = Agent(
            agent_spec=agent_spec,
            tool_registry=sub_registry,
            provider_registry=agent_provider_registry,
            provider=provider,
        )
        return agent.run(**inputs)

def find_agent(name: str) -> Optional[Path]:
    """Find an agent by name, searching all agent directories.

    Args:
        name: Agent name (without .yaml extension)

    Returns:
        Path to the agent file, or None if not found
    """
    from orac.config import Config
    return Config.find_resource(name, 'agents')


def load_agent_spec(agent_path: Union[str, Path]) -> AgentSpec:
    """Load and validate agent YAML file.

    Args:
        agent_path: Path to agent file, or agent name to search for
    """
    agent_path = Path(agent_path)

    # If path doesn't exist and doesn't look like a path, try to find by name
    if not agent_path.exists() and not agent_path.suffix:
        found = find_agent(str(agent_path))
        if found:
            agent_path = found
        else:
            raise FileNotFoundError(f"Agent not found: {agent_path}")

    with open(agent_path, 'r') as f:
        data = yaml.safe_load(f)
    return AgentSpec(**data)