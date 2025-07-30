"""
Tools execution engine for Orac.

This module provides functionality to:
- Load and validate tool specifications from YAML
- Execute Python tool scripts with proper sandboxing
- Manage tool inputs/outputs according to specifications
- Integrate with the broader Orac ecosystem
"""

from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Union
from pathlib import Path
import yaml
import importlib.util
import sys
import subprocess
import json
import tempfile
import os

from .logger import logger
from .config import Config
from .progress import ProgressCallback, ProgressEvent, ProgressType


@dataclass
class ToolInput:
    """Represents a tool input parameter."""
    name: str
    type: str = "string"
    description: str = ""
    required: bool = True
    default: Any = None


@dataclass
class ToolOutput:
    """Represents a tool output specification."""
    name: str
    type: str = "string"
    description: str = ""


@dataclass
class ToolSpec:
    """Complete tool specification loaded from YAML."""
    name: str
    description: str
    version: str
    inputs: List[ToolInput]
    outputs: List[ToolOutput]
    metadata: Dict[str, Any]
    security: Dict[str, Any]


class ToolValidationError(Exception):
    """Raised when tool validation fails."""
    pass


class ToolExecutionError(Exception):
    """Raised when tool execution fails."""
    pass


class ToolEngine:
    """Executes tools according to their specifications."""

    def __init__(self, tool_spec: ToolSpec, tools_dir: str = None,
                 progress_callback: Optional[ProgressCallback] = None):
        self.spec = tool_spec
        self.tools_dir = Path(tools_dir or Config.DEFAULT_TOOLS_DIR)
        self.progress_callback = progress_callback
        self.tool_module = None

    def _load_tool_module(self):
        """Dynamically load the tool's Python module."""
        tool_path = self.tools_dir / f"{self.spec.name}.py"

        if not tool_path.exists():
            raise ToolValidationError(f"Tool script not found: {tool_path}")

        # Load module dynamically
        spec = importlib.util.spec_from_file_location(
            f"orac.tools.{self.spec.name}",
            tool_path
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"orac.tools.{self.spec.name}"] = module
        spec.loader.exec_module(module)

        # Verify required function exists
        if not hasattr(module, 'execute'):
            raise ToolValidationError(
                f"Tool {self.spec.name} must have an 'execute' function"
            )

        self.tool_module = module

    def _validate_inputs(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and convert inputs according to specification."""
        validated = {}

        for input_spec in self.spec.inputs:
            name = input_spec.name
            value = inputs.get(name)

            if value is None:
                if input_spec.required and input_spec.default is None:
                    raise ToolValidationError(
                        f"Required input '{name}' is missing"
                    )
                value = input_spec.default

            # Type conversion (similar to Orac parameter handling)
            if value is not None:
                validated[name] = self._convert_type(
                    value, input_spec.type, name
                )

        return validated

    def _convert_type(self, value: Any, type_name: str, param_name: str) -> Any:
        """Convert value to specified type."""
        # Reuse the type conversion logic from Orac
        type_map = Config.SUPPORTED_TYPES

        if type_name not in type_map:
            return value

        try:
            if type_name in ("bool", "boolean"):
                if isinstance(value, str):
                    return value.lower() in ("true", "1", "yes", "on", "y")
                return bool(value)
            elif type_name in ("list", "array"):
                if isinstance(value, str):
                    return [v.strip() for v in value.split(",") if v.strip()]
                return list(value) if not isinstance(value, list) else value
            else:
                return type_map[type_name](value)
        except (ValueError, TypeError) as e:
            raise ToolValidationError(
                f"Cannot convert input '{param_name}' to {type_name}: {e}"
            )

    def execute(self, inputs: Dict[str, Any],
                sandbox: bool = True) -> Union[str, Dict[str, Any]]:
        """
        Execute the tool with given inputs.

        Args:
            inputs: Input parameters for the tool
            sandbox: Whether to execute in a sandboxed environment

        Returns:
            Tool output (string or dictionary)
        """
        # Emit progress start
        if self.progress_callback:
            self.progress_callback(ProgressEvent(
                type=ProgressType.TOOL_START,
                message=f"Starting tool: {self.spec.name}",
                metadata={"tool_name": self.spec.name, "inputs": inputs}
            ))

        try:
            # Validate inputs
            validated_inputs = self._validate_inputs(inputs)

            if sandbox and self.spec.security.get('timeout'):
                # Execute in subprocess with timeout
                result = self._execute_sandboxed(validated_inputs)
            else:
                # Execute directly
                self._load_tool_module()
                result = self.tool_module.execute(validated_inputs)

            # Validate outputs match specification
            self._validate_outputs(result)

            # Emit progress complete
            if self.progress_callback:
                self.progress_callback(ProgressEvent(
                    type=ProgressType.TOOL_COMPLETE,
                    message=f"Completed tool: {self.spec.name}",
                    metadata={"tool_name": self.spec.name, "result_type": type(result).__name__}
                ))

            return result

        except Exception as e:
            # Emit error event
            if self.progress_callback:
                self.progress_callback(ProgressEvent(
                    type=ProgressType.TOOL_ERROR,
                    message=f"Tool '{self.spec.name}' failed: {str(e)}",
                    metadata={"tool_name": self.spec.name, "error_type": type(e).__name__}
                ))
            raise ToolExecutionError(f"Tool execution failed: {e}")

    def _execute_sandboxed(self, inputs: Dict[str, Any]) -> Any:
        """Execute tool in a subprocess with resource limits."""
        # Create a temporary script that executes the tool
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(f"""
import sys
import json
sys.path.insert(0, '{self.tools_dir.parent}')

from tools.{self.spec.name} import execute

inputs = json.loads('{json.dumps(inputs)}')
result = execute(inputs)
print(json.dumps(result))
""")
            script_path = f.name

        try:
            # Execute with timeout
            timeout = self.spec.security.get('timeout', 30)
            result = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True
            )

            # Parse output
            return json.loads(result.stdout)

        finally:
            os.unlink(script_path)

    def _validate_outputs(self, result: Union[str, Dict[str, Any]]) -> None:
        """Validate that outputs match specification."""
        if isinstance(result, str):
            # String output is always valid
            return

        if not isinstance(result, dict):
            raise ToolValidationError(
                f"Tool must return string or dict, got {type(result)}"
            )

        # Check all specified outputs are present
        for output in self.spec.outputs:
            if output.name not in result:
                raise ToolValidationError(
                    f"Missing required output: {output.name}"
                )


def load_tool(tool_path: Union[str, Path]) -> ToolSpec:
    """Load and validate tool YAML file."""
    tool_path = Path(tool_path)

    if not tool_path.exists():
        raise ToolValidationError(f"Tool file not found: {tool_path}")

    try:
        with open(tool_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ToolValidationError(f"Invalid YAML in tool file: {e}")

    return _parse_tool_data(data)


def _parse_tool_data(data: Dict[str, Any]) -> ToolSpec:
    """Parse tool data dictionary into ToolSpec."""
    # Parse inputs
    inputs = []
    for input_data in data.get('inputs', []):
        inputs.append(ToolInput(
            name=input_data['name'],
            type=input_data.get('type', 'string'),
            description=input_data.get('description', ''),
            required=input_data.get('required', True),
            default=input_data.get('default')
        ))

    # Parse outputs
    outputs = []
    for output_data in data.get('outputs', []):
        outputs.append(ToolOutput(
            name=output_data['name'],
            type=output_data.get('type', 'string'),
            description=output_data.get('description', '')
        ))

    return ToolSpec(
        name=data['name'],
        description=data.get('description', ''),
        version=data.get('version', '1.0.0'),
        inputs=inputs,
        outputs=outputs,
        metadata=data.get('metadata', {}),
        security=data.get('security', {})
    )


def list_tools(tools_dir: Union[str, Path]) -> List[Dict[str, str]]:
    """List available tools in the tools directory."""
    tools_dir = Path(tools_dir)
    tools = []

    if not tools_dir.exists():
        return tools

    for yaml_file in tools_dir.glob("*.yaml"):
        # Skip if no corresponding .py file
        py_file = yaml_file.with_suffix('.py')
        if not py_file.exists():
            continue

        try:
            spec = load_tool(yaml_file)
            tools.append({
                'name': spec.name,
                'description': spec.description,
                'version': spec.version,
                'path': str(yaml_file)
            })
        except Exception as e:
            logger.warning(f"Failed to load tool {yaml_file}: {e}")

    return tools
