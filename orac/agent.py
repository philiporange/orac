"""
Agent engine for Orac - enables autonomous ReAct-style agents with tool usage.

Agents can specify custom API configuration in their YAML:
- provider: The LLM provider to use (e.g., 'openai', 'google')
- base_url: Custom API endpoint URL (optional, overrides provider defaults)
- api_key: API key for authentication (optional, can use environment variables)
- model_name: The model to use for agent reasoning
- tools: List of available tools (prompts, flows, skills)

Note: Command-line flags and programmatic parameters override YAML values.
"""

import yaml
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from string import Template

from .config import Config, Provider
from .registry import ToolRegistry, RegisteredTool
from .openai_client import call_api
from .providers import ProviderRegistry
from .prompt import Prompt, _inject_response_format
from .flow import Flow, load_flow
from .skill import Skill, load_skill
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

class Agent:
    def __init__(self, agent_spec: AgentSpec, tool_registry: ToolRegistry, provider_registry: ProviderRegistry, provider: Optional[Provider] = None):
        self.spec = agent_spec
        self.registry = tool_registry
        self.provider_registry = provider_registry
        self.provider = provider
        self.message_history: List[Dict[str, str]] = []

    def run(self, **kwargs) -> str:
        """Executes the agent's ReAct loop to achieve its goal."""
        
        # 1. Format the initial system prompt with inputs and tool list
        tool_specs = self.registry.get_tools_spec(self.spec.tools)
        
        # We start with an empty history for the template, it will be built in the loop
        initial_prompt_template = Template(self.spec.system_prompt)
        system_prompt = initial_prompt_template.safe_substitute(
            tool_list=tool_specs, 
            history="", 
            **kwargs
        )
        
        # Add an initial user message to start the conversation with the provided parameters
        input_summary = ", ".join([f"{k}={v}" for k, v in kwargs.items()])
        self.message_history.append({'role': 'user', 'text': f"Please help me with the following inputs: {input_summary}"})
        
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

            # 2. Query the LLM for the next action
            try:
                # Convert response_mime_type to response_format for OpenAI compatibility
                processed_config = _inject_response_format(self.spec.generation_config)
                response_str = call_api(
                    provider_registry=self.provider_registry,
                    provider=self.provider,
                    message_history=self.message_history,
                    system_prompt=system_prompt,
                    model_name=self.spec.model_name,
                    generation_config=processed_config
                )
                action_data = json.loads(response_str)
            except Exception as e:
                print(f"ERROR: Failed to get valid action from LLM: {e}")
                self.message_history.append({'role': 'user', 'text': f"Observation: Invalid action response. Error: {e}"})
                continue
            
            thought = action_data.get("thought", "No thought provided.")
            tool_name = action_data.get("tool")
            tool_inputs = action_data.get("inputs", {})

            print(f"🤔 Thought: {thought}")
            self.message_history.append({'role': 'model', 'text': json.dumps(action_data, indent=2)})

            if not tool_name:
                print("ERROR: LLM did not provide a tool name.")
                self.message_history.append({'role': 'user', 'text': "Observation: No tool was selected. You must select a tool."})
                continue

            # 3. Handle the 'finish' action
            if tool_name == "tool:finish":
                final_answer = tool_inputs.get("result", "Agent finished without a final answer.")
                print(f"✅ Agent Finished: {final_answer}")
                return final_answer
            
            # 4. Execute the chosen tool
            print(f"🎬 Action: {tool_name} with inputs: {tool_inputs}")
            observation = self._execute_tool(tool_name, tool_inputs)
            
            # 5. Add observation to history and repeat
            print(f"👀 Observation: {observation}")
            self.message_history.append({'role': 'user', 'text': f"Observation: {str(observation)}"})
            
        final_message = "Agent stopped: Maximum iterations reached."
        print(final_message)
        return final_message

    def _execute_tool(self, tool_name: str, tool_inputs: Dict[str, Any]) -> str:
        """Execute a tool and return the observation."""
        tool = self.registry.get_tool(tool_name)
        if not tool:
            return f"Error: Tool '{tool_name}' not found."
        
        try:
            if tool.type == "prompt":
                prompt_instance = Prompt(tool.name, prompts_dir=self.registry.prompts_dir, provider=self.provider.value if self.provider else None)
                return prompt_instance.completion(**tool_inputs)
            elif tool.type == "flow":
                flow_spec = load_flow(tool.file_path)
                flow_engine = Flow(flow_spec)
                return flow_engine.execute(tool_inputs)
            elif tool.type == "tool":
                skill_spec = load_skill(tool.file_path)
                skill_engine = Skill(skill_spec)
                return skill_engine.execute(tool_inputs)
            else:
                return f"Error: Unknown tool type '{tool.type}'"
        except Exception as e:
            return f"Error executing tool '{tool_name}': {e}"

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