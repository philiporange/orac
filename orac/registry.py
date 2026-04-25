"""Unified discovery registry for Orac prompts, flows, skills, teams, and agents.

The registry loads executable YAML resources from Orac's layered resource
directories: project resources first, then user resources, then package
resources. Higher-priority resources shadow lower-priority resources with the
same tool key while preserving direct-directory overrides for tests and custom
callers.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional, Iterable
import yaml
from .config import Config

@dataclass
class RegisteredTool:
    name: str
    type: str  # "prompt", "flow", "tool", or "agent"
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
        skills_dir: Optional[str] = None,
        teams_dir: Optional[str] = None,
        agents_dir: Optional[str] = None,
        prompts_dirs: Optional[Iterable[str]] = None,
        flows_dirs: Optional[Iterable[str]] = None,
        tools_dirs: Optional[Iterable[str]] = None,
        skills_dirs: Optional[Iterable[str]] = None,
        teams_dirs: Optional[Iterable[str]] = None,
        agents_dirs: Optional[Iterable[str]] = None,
    ):
        tools_dir = tools_dir or skills_dir
        tools_dirs = tools_dirs or skills_dirs

        self.prompts_dirs = self._resolve_dirs(prompts_dir, prompts_dirs, Config.get_prompts_dirs)
        self.flows_dirs = self._resolve_dirs(flows_dir, flows_dirs, Config.get_flows_dirs)
        self.tools_dirs = self._resolve_dirs(tools_dir, tools_dirs, Config.get_skills_dirs)
        self.teams_dirs = self._resolve_dirs(teams_dir, teams_dirs, Config.get_teams_dirs)
        self.agents_dirs = self._resolve_dirs(agents_dir, agents_dirs, Config.get_agents_dirs)

        self.prompts_dir = self.prompts_dirs[0]
        self.flows_dir = self.flows_dirs[0]
        self.tools_dir = self.tools_dirs[0]
        self.teams_dir = self.teams_dirs[0]
        self.agents_dir = self.agents_dirs[0]
        self.tools: Dict[str, RegisteredTool] = {}
        self._load_all()

    @staticmethod
    def _resolve_dirs(single_dir, multiple_dirs, default_dirs):
        """Return normalized resource directories in priority order."""
        if multiple_dirs is not None:
            dirs = multiple_dirs
        elif single_dir is not None:
            dirs = [single_dir]
        else:
            dirs = default_dirs()
        return [Path(directory) for directory in dirs]

    def _load_all(self):
        self._load_prompts()
        self._load_flows()
        self._load_tools()
        self._load_teams()
        self._load_agents()

    def _load_from_dirs(self, directories: List[Path], tool_type: str):
        for directory in directories:
            self._load_from_dir(directory, tool_type)

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
                if tool_key in self.tools:
                    continue
                self.tools[tool_key] = RegisteredTool(
                    name=name,
                    type=tool_type,
                    description=spec.get("description", "No description provided."),
                    inputs=spec.get("parameters", spec.get("inputs", [])),
                    outputs=spec.get("outputs", []),
                    file_path=yaml_file,
                )

    def _load_prompts(self):
        self._load_from_dirs(self.prompts_dirs, "prompt")

    def _load_flows(self):
        self._load_from_dirs(self.flows_dirs, "flow")
        
    def _load_tools(self):
        self._load_from_dirs(self.tools_dirs, "tool")
        
    def _load_teams(self):
        self._load_from_dirs(self.teams_dirs, "team")

    def _load_agents(self):
        self._load_from_dirs(self.agents_dirs, "agent")

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
