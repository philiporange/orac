"""
Skills execution engine for Orac.

This module provides functionality to:
- Load and validate skill specifications from YAML
- Execute Python skill scripts with proper sandboxing
- Manage skill inputs/outputs according to specifications
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
class SkillInput:
    """Represents a skill input parameter."""
    name: str
    type: str = "string"
    description: str = ""
    required: bool = True
    default: Any = None


@dataclass
class SkillOutput:
    """Represents a skill output specification."""
    name: str
    type: str = "string"
    description: str = ""


@dataclass
class SkillSpec:
    """Complete skill specification loaded from YAML."""
    name: str
    description: str
    version: str
    inputs: List[SkillInput]
    outputs: List[SkillOutput]
    metadata: Dict[str, Any]
    security: Dict[str, Any]


class SkillValidationError(Exception):
    """Raised when skill validation fails."""
    pass


class SkillExecutionError(Exception):
    """Raised when skill execution fails."""
    pass


class SkillEngine:
    """Executes skills according to their specifications."""

    def __init__(self, skill_spec: SkillSpec, skills_dir: str = None,
                 progress_callback: Optional[ProgressCallback] = None):
        self.spec = skill_spec
        self.skills_dir = Path(skills_dir or Config.DEFAULT_SKILLS_DIR)
        self.progress_callback = progress_callback
        self.skill_module = None

    def _load_skill_module(self):
        """Dynamically load the skill's Python module."""
        skill_path = self.skills_dir / f"{self.spec.name}.py"

        if not skill_path.exists():
            raise SkillValidationError(f"Skill script not found: {skill_path}")

        # Load module dynamically
        spec = importlib.util.spec_from_file_location(
            f"orac.skills.{self.spec.name}",
            skill_path
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"orac.skills.{self.spec.name}"] = module
        spec.loader.exec_module(module)

        # Verify required function exists
        if not hasattr(module, 'execute'):
            raise SkillValidationError(
                f"Skill {self.spec.name} must have an 'execute' function"
            )

        self.skill_module = module

    def _validate_inputs(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and convert inputs according to specification."""
        validated = {}

        for input_spec in self.spec.inputs:
            name = input_spec.name
            value = inputs.get(name)

            if value is None:
                if input_spec.required and input_spec.default is None:
                    raise SkillValidationError(
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
            raise SkillValidationError(
                f"Cannot convert input '{param_name}' to {type_name}: {e}"
            )

    def execute(self, inputs: Dict[str, Any],
                sandbox: bool = True) -> Union[str, Dict[str, Any]]:
        """
        Execute the skill with given inputs.

        Args:
            inputs: Input parameters for the skill
            sandbox: Whether to execute in a sandboxed environment

        Returns:
            Skill output (string or dictionary)
        """
        # Emit progress start
        if self.progress_callback:
            self.progress_callback(ProgressEvent(
                type=ProgressType.SKILL_START,
                message=f"Starting skill: {self.spec.name}",
                metadata={"skill_name": self.spec.name, "inputs": inputs}
            ))

        try:
            # Validate inputs
            validated_inputs = self._validate_inputs(inputs)

            if sandbox and self.spec.security.get('timeout'):
                # Execute in subprocess with timeout
                result = self._execute_sandboxed(validated_inputs)
            else:
                # Execute directly
                self._load_skill_module()
                result = self.skill_module.execute(validated_inputs)

            # Validate outputs match specification
            self._validate_outputs(result)

            # Emit progress complete
            if self.progress_callback:
                self.progress_callback(ProgressEvent(
                    type=ProgressType.SKILL_COMPLETE,
                    message=f"Completed skill: {self.spec.name}",
                    metadata={"skill_name": self.spec.name, "result_type": type(result).__name__}
                ))

            return result

        except Exception as e:
            # Emit error event
            if self.progress_callback:
                self.progress_callback(ProgressEvent(
                    type=ProgressType.SKILL_ERROR,
                    message=f"Skill '{self.spec.name}' failed: {str(e)}",
                    metadata={"skill_name": self.spec.name, "error_type": type(e).__name__}
                ))
            raise SkillExecutionError(f"Skill execution failed: {e}")

    def _execute_sandboxed(self, inputs: Dict[str, Any]) -> Any:
        """Execute skill in a subprocess with resource limits."""
        # Create a temporary script that executes the skill
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(f"""
import sys
import json
sys.path.insert(0, '{self.skills_dir.parent}')

from skills.{self.spec.name} import execute

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
            raise SkillValidationError(
                f"Skill must return string or dict, got {type(result)}"
            )

        # Check all specified outputs are present
        for output in self.spec.outputs:
            if output.name not in result:
                raise SkillValidationError(
                    f"Missing required output: {output.name}"
                )


def load_skill(skill_path: Union[str, Path]) -> SkillSpec:
    """Load and validate skill YAML file."""
    skill_path = Path(skill_path)

    if not skill_path.exists():
        raise SkillValidationError(f"Skill file not found: {skill_path}")

    try:
        with open(skill_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise SkillValidationError(f"Invalid YAML in skill file: {e}")

    return _parse_skill_data(data)


def _parse_skill_data(data: Dict[str, Any]) -> SkillSpec:
    """Parse skill data dictionary into SkillSpec."""
    # Parse inputs
    inputs = []
    for input_data in data.get('inputs', []):
        inputs.append(SkillInput(
            name=input_data['name'],
            type=input_data.get('type', 'string'),
            description=input_data.get('description', ''),
            required=input_data.get('required', True),
            default=input_data.get('default')
        ))

    # Parse outputs
    outputs = []
    for output_data in data.get('outputs', []):
        outputs.append(SkillOutput(
            name=output_data['name'],
            type=output_data.get('type', 'string'),
            description=output_data.get('description', '')
        ))

    return SkillSpec(
        name=data['name'],
        description=data.get('description', ''),
        version=data.get('version', '1.0.0'),
        inputs=inputs,
        outputs=outputs,
        metadata=data.get('metadata', {}),
        security=data.get('security', {})
    )


def list_skills(skills_dir: Union[str, Path]) -> List[Dict[str, str]]:
    """List available skills in the skills directory."""
    skills_dir = Path(skills_dir)
    skills = []

    if not skills_dir.exists():
        return skills

    for yaml_file in skills_dir.glob("*.yaml"):
        # Skip if no corresponding .py file
        py_file = yaml_file.with_suffix('.py')
        if not py_file.exists():
            continue

        try:
            spec = load_skill(yaml_file)
            skills.append({
                'name': spec.name,
                'description': spec.description,
                'version': spec.version,
                'path': str(yaml_file)
            })
        except Exception as e:
            logger.warning(f"Failed to load skill {yaml_file}: {e}")

    return skills
