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

from __future__ import annotations

import re
import yaml
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Callable, Literal, Optional, Union
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

AgentEventType = Literal[
    "iteration_start",
    "model_action",
    "tool_start",
    "tool_finish",
    "invalid_action",
    "finish",
    "max_iterations",
]


@dataclass
class AgentEvent:
    """Structured event emitted by Agent.run / Agent.continue_with.

    Attached via the optional `event_callback` argument on Agent. Used by
    debugging tools and external harnesses (e.g. the orac_improver project)
    to observe ReAct iterations, tool calls, and termination conditions
    without tailing stdout.
    """
    type: AgentEventType
    timestamp: datetime
    iteration: Optional[int] = None
    payload: Dict[str, Any] = field(default_factory=dict)


AgentEventCallback = Callable[[AgentEvent], None]


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
    thinking: Optional[bool] = None
    reasoning_effort: Optional[str] = None
    max_iterations: int = 15
    compact_after_messages: int = 12
    compact_keep_recent: int = 4
    summarization_model: Optional[str] = None
    compact_time_gap_seconds: int = 300

class Agent:
    def __init__(
        self,
        agent_spec: AgentSpec,
        tool_registry: ToolRegistry,
        provider_registry: ProviderRegistry,
        provider: Optional[Provider] = None,
        event_callback: Optional[AgentEventCallback] = None,
    ):
        self.spec = agent_spec
        self.registry = tool_registry
        self.provider_registry = provider_registry
        self.provider = provider
        self.event_callback = event_callback
        self.message_history: List[Dict[str, str]] = []
        self.total_usage: Optional[Usage] = None
        self.last_message_time: Optional[datetime] = None
        self._system_prompt: Optional[str] = None

    def _emit(
        self,
        type_: AgentEventType,
        iteration: Optional[int] = None,
        **payload: Any,
    ) -> None:
        if not self.event_callback:
            return
        try:
            self.event_callback(AgentEvent(
                type=type_,
                timestamp=datetime.now(),
                iteration=iteration,
                payload=payload,
            ))
        except Exception as e:
            logger.warning(f"Agent event callback raised: {e}")

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

    def _normalize_tool_name(self, tool_name: str) -> str:
        """Resolve unprefixed tool names when they match one registered tool."""
        if not tool_name or ":" in tool_name:
            return tool_name

        candidates = [
            registered_name
            for registered_name in self.registry.tools
            if registered_name.rsplit(":", 1)[-1] == tool_name
        ]
        if len(candidates) == 1:
            return candidates[0]

        preferred_tool = f"tool:{tool_name}"
        if preferred_tool in self.registry.tools:
            return preferred_tool

        return tool_name

    def _build_system_prompt(self, **kwargs) -> str:
        """Render the system prompt template with tool list and input vars."""
        tool_specs = self.registry.get_tools_spec(self.spec.tools)
        template_vars = {"tool_list": tool_specs, "history": ""}
        template_vars.update(kwargs)
        return Template(self.spec.system_prompt).safe_substitute(**template_vars)

    def run(self, include_usage: bool = False, **kwargs) -> str | CompletionResult:
        """Executes the agent's ReAct loop to achieve its goal."""

        self._system_prompt = self._build_system_prompt(**kwargs)

        # Add an initial user message to start the conversation with the provided parameters
        input_summary = ", ".join([f"{k}={v}" for k, v in kwargs.items()])
        self._append_message('user', f"Please help me with the following inputs: {input_summary}")

        return self._run_loop(self._system_prompt, include_usage=include_usage)

    def continue_with(self, user_message: str, include_usage: bool = False) -> str | CompletionResult:
        """Append a user message to existing history and resume the ReAct loop.

        Used by chat/dialogue harnesses (e.g. orac_improver) to drive an agent
        turn-by-turn after an initial run(). Reuses the system prompt that was
        rendered on the first run().
        """
        if self._system_prompt is None:
            raise RuntimeError(
                "continue_with() requires run() to have been called first to "
                "establish the system prompt."
            )
        self._append_message('user', user_message)
        return self._run_loop(self._system_prompt, include_usage=include_usage)

    def _run_loop(self, system_prompt: str, include_usage: bool) -> str | CompletionResult:
        """The ReAct iteration loop. Runs until tool:finish or max_iterations."""
        for i in range(self.spec.max_iterations):
            print(f"\n--- Iteration {i+1}/{self.spec.max_iterations} ---")
            self._emit("iteration_start", iteration=i + 1)

            # 1. Compact history if needed (before sending to LLM)
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

            # 2. Query the LLM for the next action
            try:
                # Convert response_mime_type to response_format for OpenAI compatibility
                processed_config = _inject_response_format(self.spec.generation_config)
                completion_result = call_api(
                    provider_registry=self.provider_registry,
                    provider=self.provider,
                    message_history=self.message_history,
                    system_prompt=system_prompt,
                    model_name=self.spec.model_name,
                    generation_config=processed_config,
                    thinking=self.spec.thinking,
                    reasoning_effort=self.spec.reasoning_effort,
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
                self._emit("invalid_action", iteration=i + 1, error=str(e))
                self._append_message('user', f"Observation: Invalid action response. Error: {e}")
                continue

            thought = action_data.get("thought", "No thought provided.")
            raw_tool_name = action_data.get("tool")
            tool_name = self._normalize_tool_name(raw_tool_name)
            tool_inputs = action_data.get("inputs", {})
            pin_observation = action_data.get("pin", False)

            print(f"🤔 Thought: {thought}")
            self._emit("model_action", iteration=i + 1, action=action_data)
            self._append_message('model', json.dumps(action_data, indent=2))

            if not tool_name:
                print("ERROR: LLM did not provide a tool name.")
                self._emit("invalid_action", iteration=i + 1, error="no tool name")
                self._append_message('user', "Observation: No tool was selected. You must select a tool.")
                continue

            # 3. Handle the 'finish' action
            if tool_name == "tool:finish":
                final_answer = tool_inputs.get("result", "Agent finished without a final answer.")
                print(f"✅ Agent Finished: {final_answer}")
                self._emit("finish", iteration=i + 1, result=final_answer)
                if include_usage:
                    return CompletionResult(text=final_answer, usage=self.total_usage)
                return final_answer

            # 4. Execute the chosen tool
            print(f"🎬 Action: {tool_name} with inputs: {tool_inputs}")
            self._emit("tool_start", iteration=i + 1, tool=tool_name, inputs=tool_inputs)
            observation = self._execute_tool(tool_name, tool_inputs)
            self._emit("tool_finish", iteration=i + 1, tool=tool_name, observation=str(observation))

            # 5. Add observation to history and repeat
            print(f"👀 Observation: {observation}")
            self._append_message('user', f"Observation: {str(observation)}",
                                 pinned=bool(pin_observation))

        final_message = "Agent stopped: Maximum iterations reached."
        print(final_message)
        self._emit("max_iterations", iteration=self.spec.max_iterations)
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
                flow_engine = Flow(flow_spec, provider=self.provider)
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
        # Honor custom api_key/base_url from the agent YAML; fall back to the
        # environment key when no direct key is given.
        agent_provider_registry.add_provider(
            provider,
            api_key=agent_spec.api_key,
            base_url=agent_spec.base_url,
            allow_env=True,
            interactive=False,
        )

        def registry_dirs(plural_name: str, singular_name: str) -> List[Path]:
            dirs = getattr(self.registry, plural_name, None)
            if dirs is not None:
                try:
                    resolved = list(dirs)
                    if resolved:
                        return resolved
                except TypeError:
                    pass
            single = getattr(self.registry, singular_name, None)
            return [single] if single is not None else []

        sub_registry = ToolRegistry(
            prompts_dirs=registry_dirs("prompts_dirs", "prompts_dir"),
            flows_dirs=registry_dirs("flows_dirs", "flows_dir"),
            tools_dirs=registry_dirs("tools_dirs", "tools_dir"),
            teams_dirs=registry_dirs("teams_dirs", "teams_dir"),
            agents_dirs=registry_dirs("agents_dirs", "agents_dir"),
        )

        agent = Agent(
            agent_spec=agent_spec,
            tool_registry=sub_registry,
            provider_registry=agent_provider_registry,
            provider=provider,
        )
        result = agent.run(include_usage=True, **inputs)
        return self._absorb_subagent_result(result)

    def _absorb_subagent_result(self, result: Any) -> str:
        """Fold a subagent's usage into our running total and return its text."""
        if isinstance(result, CompletionResult):
            if result.usage is not None:
                self.total_usage = (
                    (self.total_usage + result.usage)
                    if self.total_usage
                    else result.usage
                )
            return result.text
        return result

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
