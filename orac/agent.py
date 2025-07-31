import yaml
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional
from string import Template

from .config import Config, Provider
from .registry import ToolRegistry, RegisteredTool
from .client import call_api
from .prompt import Prompt, _inject_response_format
from .flow import FlowEngine, load_flow
from .skills import SkillEngine, load_skill
from .logger import logger

@dataclass
class AgentSpec:
    name: str
    description: str
    system_prompt: str
    inputs: List[Dict[str, Any]] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    model_name: str = "gemini-2.5-pro"
    generation_config: Dict[str, Any] = field(default_factory=dict)
    max_iterations: int = 15

class AgentEngine:
    def __init__(self, agent_spec: AgentSpec, tool_registry: ToolRegistry, provider: Provider, api_key: Optional[str] = None):
        self.spec = agent_spec
        self.registry = tool_registry
        self.provider = provider
        self.api_key = api_key
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
        
        for i in range(self.spec.max_iterations):
            print(f"\n--- Iteration {i+1}/{self.spec.max_iterations} ---")

            # 2. Query the LLM for the next action
            try:
                # Convert response_mime_type to response_format for OpenAI compatibility
                processed_config = _inject_response_format(self.spec.generation_config)
                response_str = call_api(
                    provider=self.provider,
                    api_key=self.api_key,
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
            tool = self.registry.get_tool(tool_name)
            if not tool:
                observation = f"Error: Tool '{tool_name}' not found."
            else:
                try:
                    if tool.type == "prompt":
                        prompt_instance = Prompt(tool.name, prompts_dir=self.registry.prompts_dir, provider=self.provider.value, api_key=self.api_key)
                        observation = prompt_instance.completion(**tool_inputs)
                    elif tool.type == "flow":
                        flow_spec = load_flow(tool.file_path)
                        flow_engine = FlowEngine(flow_spec)
                        observation = flow_engine.execute(tool_inputs)
                    elif tool.type == "tool":
                        skill_spec = load_skill(tool.file_path)
                        skill_engine = SkillEngine(skill_spec)
                        observation = skill_engine.execute(tool_inputs)
                    else:
                        observation = f"Error: Unknown tool type '{tool.type}'"
                except Exception as e:
                    observation = f"Error executing tool '{tool_name}': {e}"
            
            # 5. Add observation to history and repeat
            print(f"👀 Observation: {observation}")
            self.message_history.append({'role': 'user', 'text': f"Observation: {str(observation)}"})
            
        final_message = "Agent stopped: Maximum iterations reached."
        print(final_message)
        return final_message

def load_agent_spec(agent_path: Path) -> AgentSpec:
    with open(agent_path, 'r') as f:
        data = yaml.safe_load(f)
    return AgentSpec(**data)