from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional
import yaml
from .config import Config

@dataclass
class RegisteredTool:
    name: str
    type: str  # "prompt", "flow", or "tool"
    description: str
    inputs: List[Dict[str, Any]] = field(default_factory=list)
    outputs: List[Dict[str, Any]] = field(default_factory=list)
    file_path: Path = None

class ToolRegistry:
    """Discovers and provides a unified interface for all executable resources."""

    def __init__(
        self,
        prompts_dir: Optional[str] = None,
        flows_dir: Optional[str] = None,
        tools_dir: Optional[str] = None,
    ):
        self.prompts_dir = Path(prompts_dir) if prompts_dir else Config.get_prompts_dir()
        self.flows_dir = Path(flows_dir) if flows_dir else Config.get_flows_dir()
        self.tools_dir = Path(tools_dir) if tools_dir else Config.get_skills_dir()
        self.tools: Dict[str, RegisteredTool] = {}
        self._load_all()

    def _load_all(self):
        self._load_prompts()
        self._load_flows()
        self._load_tools()

    def _load_from_dir(self, directory: Path, tool_type: str):
        if not directory.exists():
            return
        for yaml_file in directory.glob("*.yaml"):
            with open(yaml_file, "r") as f:
                spec = yaml.safe_load(f)
                if not spec:
                    continue
                
                # Use the filename (stem) as the name if not specified in the YAML
                name = spec.get('name', yaml_file.stem)
                
                # The agent identifies tools by `type:name` (e.g., `prompt:capital`)
                tool_key = f"{tool_type}:{name}"
                self.tools[tool_key] = RegisteredTool(
                    name=name,
                    type=tool_type,
                    description=spec.get("description", "No description provided."),
                    inputs=spec.get("parameters", spec.get("inputs", [])),
                    outputs=spec.get("outputs", []),
                    file_path=yaml_file,
                )

    def _load_prompts(self):
        self._load_from_dir(self.prompts_dir, "prompt")

    def _load_flows(self):
        self._load_from_dir(self.flows_dir, "flow")
        
    def _load_tools(self):
        self._load_from_dir(self.tools_dir, "tool")

    def get_tool(self, tool_name: str) -> Optional[RegisteredTool]:
        return self.tools.get(tool_name)

    def get_tools_spec(self, tool_names: List[str]) -> str:
        """Formats the specification for a list of tools for the LLM prompt."""
        spec_lines = []
        for name in tool_names:
            tool = self.get_tool(name)
            if not tool:
                continue
            
            spec_lines.append(f"# Tool: {name}")
            spec_lines.append(f"# Description: {tool.description}")
            if tool.inputs:
                inputs_str = ", ".join([f"{i['name']} ({i.get('type', 'string')})" for i in tool.inputs])
                spec_lines.append(f"# Inputs: {inputs_str}")
            else:
                spec_lines.append(f"# Inputs: None")
            spec_lines.append("") # Newline for readability
        
        return "\n".join(spec_lines)