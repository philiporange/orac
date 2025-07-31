"""
Flow engine for Orac - enables chaining multiple prompts in a DAG structure.

This module provides classes and functions for:
- Loading and validating flow YAML specifications
- Building dependency graphs from flow definitions
- Executing flows with proper step ordering and result passing
- Template variable resolution for dynamic input mapping

Flows use the Prompt class to execute individual steps.
"""

import re
import yaml
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Set, Union
from pathlib import Path
import networkx as nx

from .logger import logger
from .prompt import Prompt
from .skills import SkillEngine, load_skill
from .progress import ProgressCallback, ProgressEvent, ProgressType


@dataclass
class FlowInput:
    """Represents a flow input parameter."""
    name: str
    type: str = "string"
    description: str = ""
    required: bool = True
    default: Any = None


@dataclass
class FlowOutput:
    """Represents a flow output mapping."""
    name: str
    source: str  # Format: "step_name.output_name"
    description: str = ""


@dataclass
class FlowStep:
    """Represents a single step in a flow."""
    name: str
    prompt_name: Optional[str] = None
    skill_name: Optional[str] = None
    inputs: Dict[str, str] = field(default_factory=dict)
    outputs: List[str] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)
    when: Optional[str] = None  # Conditional execution (future feature)


@dataclass
class FlowSpec:
    """Complete flow specification loaded from YAML."""
    name: str
    description: str
    inputs: List[FlowInput]
    outputs: List[FlowOutput]
    steps: Dict[str, FlowStep]


class FlowValidationError(Exception):
    """Raised when flow validation fails."""
    pass


class FlowExecutionError(Exception):
    """Raised when flow execution fails."""
    pass


class FlowEngine:
    """Executes flows by managing step dependencies and data flow."""

    def __init__(self, flow_spec: FlowSpec, prompts_dir: str = "prompts", 
                 skills_dir: str = "skills",
                 progress_callback: Optional[ProgressCallback] = None):
        self.spec = flow_spec
        self.prompts_dir = prompts_dir
        self.skills_dir = skills_dir
        self.progress_callback = progress_callback
        self.results: Dict[str, Dict[str, Any]] = {}
        self.graph = self._build_dependency_graph()
        self.execution_order = self._get_execution_order()

    def _build_dependency_graph(self) -> nx.DiGraph:
        """Build DAG from step dependencies and data flow."""
        logger.debug(f"Building dependency graph for flow: {self.spec.name}")
        graph = nx.DiGraph()
        
        # Add all steps as nodes
        for step_name in self.spec.steps:
            graph.add_node(step_name)
        
        # Add explicit dependencies
        for step_name, step in self.spec.steps.items():
            for dep in step.depends_on:
                if dep not in self.spec.steps:
                    raise FlowValidationError(
                        f"Step '{step_name}' depends on unknown step '{dep}'"
                    )
                graph.add_edge(dep, step_name)
        
        # Add implicit dependencies from data flow
        for step_name, step in self.spec.steps.items():
            for input_template in step.inputs.values():
                referenced_steps = self._extract_step_references(input_template)
                for ref_step in referenced_steps:
                    if ref_step not in self.spec.steps:
                        raise FlowValidationError(
                            f"Step '{step_name}' references unknown step '{ref_step}'"
                        )
                    if not graph.has_edge(ref_step, step_name):
                        graph.add_edge(ref_step, step_name)
        
        # Check for cycles
        if not nx.is_directed_acyclic_graph(graph):
            raise FlowValidationError("Workflow contains dependency cycles")
        
        logger.debug(f"Dependency graph built with {len(graph.nodes)} nodes and {len(graph.edges)} edges")
        return graph

    def _extract_step_references(self, template: str) -> Set[str]:
        """Extract step references from template string (e.g., ${step.output})."""
        pattern = r'\$\{(\w+)\.[\w.]+\}'
        matches = re.findall(pattern, template)
        # Filter out 'inputs' as it's not a step
        return {match for match in matches if match != 'inputs'}

    def _get_execution_order(self) -> List[str]:
        """Get topologically sorted execution order."""
        try:
            return list(nx.topological_sort(self.graph))
        except nx.NetworkXError as e:
            raise FlowValidationError(f"Failed to determine execution order: {e}")

    def _resolve_template(self, template: str, context: Dict[str, Any]) -> str:
        """Resolve ${var} references in templates."""
        logger.debug(f"Resolving template: {template}")
        
        def replace_var(match):
            var_path = match.group(1)
            parts = var_path.split('.')
            
            try:
                value = context
                for part in parts:
                    value = value[part]
                return str(value)
            except (KeyError, TypeError) as e:
                raise FlowExecutionError(
                    f"Failed to resolve template variable '{var_path}': {e}"
                )
        
        pattern = r'\$\{([^}]+)\}'
        resolved = re.sub(pattern, replace_var, template)
        logger.debug(f"Resolved to: {resolved}")
        return resolved

    def _build_context(self, flow_inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Build context for template resolution."""
        context = {
            'inputs': flow_inputs,
        }
        
        # Add step results
        for step_name, step_results in self.results.items():
            context[step_name] = step_results
        
        return context

    def _execute_step(self, step_name: str, context: Dict[str, Any], step_index: int = 0, total_steps: int = 0) -> Dict[str, Any]:
        """Execute a single flow step."""
        logger.info(f"Executing flow step: {step_name}")
        step = self.spec.steps[step_name]
        
        # Emit step start progress
        if self.progress_callback:
            self.progress_callback(ProgressEvent(
                type=ProgressType.FLOW_STEP_START,
                message=f"Executing step: {step_name}",
                current_step=step_index + 1,
                total_steps=total_steps,
                step_name=step_name,
                metadata={"step_name": step_name, "prompt_name": step.prompt_name, "skill_name": step.skill_name}
            ))
        
        # Resolve input templates
        resolved_inputs = {}
        for param_name, template in step.inputs.items():
            resolved_inputs[param_name] = self._resolve_template(template, context)
        
        logger.debug(f"Step '{step_name}' resolved inputs: {resolved_inputs}")
        
        # Execute the prompt or skill
        try:
            if step.prompt_name:
                # Execute a prompt step
                prompt = Prompt(step.prompt_name, prompts_dir=self.prompts_dir,
                               progress_callback=self.progress_callback)
                result = prompt(**resolved_inputs)
                
                # Handle different result types
                if isinstance(result, dict):
                    step_results = result
                else:
                    # For string results, create a dict with the first output name
                    if step.outputs:
                        step_results = {step.outputs[0]: result}
                    else:
                        step_results = {'result': result}
            elif step.skill_name:
                # Execute a skill step
                skill_path = Path(self.skills_dir) / f"{step.skill_name}.yaml"
                skill_spec = load_skill(skill_path)
                skill_engine = SkillEngine(skill_spec, skills_dir=self.skills_dir, progress_callback=self.progress_callback)
                step_results = skill_engine.execute(resolved_inputs)
            else:
                raise FlowExecutionError(f"Step '{step_name}' has no prompt or skill defined.")

            logger.debug(f"Step '{step_name}' results: {step_results}")
            
            # Emit step completion progress
            if self.progress_callback:
                self.progress_callback(ProgressEvent(
                    type=ProgressType.FLOW_STEP_COMPLETE,
                    message=f"Completed step: {step_name}",
                    current_step=step_index + 1,
                    total_steps=total_steps,
                    step_name=step_name,
                    metadata={"step_name": step_name, "result_keys": list(step_results.keys())}
                ))
            
            return step_results
            
        except Exception as e:
            if self.progress_callback:
                self.progress_callback(ProgressEvent(
                    type=ProgressType.FLOW_ERROR,
                    message=f"Step '{step_name}' failed: {str(e)}",
                    current_step=step_index + 1,
                    total_steps=total_steps,
                    step_name=step_name,
                    metadata={"step_name": step_name, "error_type": type(e).__name__}
                ))
            raise FlowExecutionError(f"Step '{step_name}' failed: {e}")

    def execute(self, inputs: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
        """Execute the flow and return final outputs."""
        logger.info(f"Starting flow execution: {self.spec.name}")
        
        # Emit flow start progress
        if self.progress_callback:
            self.progress_callback(ProgressEvent(
                type=ProgressType.FLOW_START,
                message=f"Starting flow: {self.spec.name}",
                total_steps=len(self.execution_order),
                metadata={
                    "flow_name": self.spec.name,
                    "total_steps": len(self.execution_order),
                    "execution_order": self.execution_order,
                    "dry_run": dry_run
                }
            ))
        
        if dry_run:
            logger.info(f"DRY RUN - Execution order: {' -> '.join(self.execution_order)}")
            return {}
        
        try:
            # Validate inputs
            self._validate_inputs(inputs)
            
            # Execute steps in dependency order
            for i, step_name in enumerate(self.execution_order):
                context = self._build_context(inputs)
                step_results = self._execute_step(step_name, context, i, len(self.execution_order))
                self.results[step_name] = step_results
            
            # Build final outputs
            final_outputs = {}
            for output in self.spec.outputs:
                try:
                    parts = output.source.split('.')
                    if len(parts) != 2:
                        raise FlowExecutionError(
                            f"Invalid output source format '{output.source}'. Expected 'step.output'"
                        )
                    
                    step_name, output_name = parts
                    if step_name not in self.results:
                        raise FlowExecutionError(f"Output references unknown step '{step_name}'")
                    
                    if output_name not in self.results[step_name]:
                        raise FlowExecutionError(
                            f"Output '{output_name}' not found in step '{step_name}' results"
                        )
                    
                    final_outputs[output.name] = self.results[step_name][output_name]
                    
                except Exception as e:
                    raise FlowExecutionError(f"Failed to resolve output '{output.name}': {e}")
            
            logger.info(f"Flow completed successfully with {len(final_outputs)} outputs")
            
            # Emit flow completion progress
            if self.progress_callback:
                self.progress_callback(ProgressEvent(
                    type=ProgressType.FLOW_COMPLETE,
                    message=f"Completed flow: {self.spec.name}",
                    current_step=len(self.execution_order),
                    total_steps=len(self.execution_order),
                    metadata={
                        "flow_name": self.spec.name,
                        "outputs": list(final_outputs.keys()),
                        "total_steps_completed": len(self.execution_order)
                    }
                ))
            
            return final_outputs
            
        except Exception as e:
            # Emit flow error progress
            if self.progress_callback:
                self.progress_callback(ProgressEvent(
                    type=ProgressType.FLOW_ERROR,
                    message=f"Flow '{self.spec.name}' failed: {str(e)}",
                    metadata={
                        "flow_name": self.spec.name,
                        "error_type": type(e).__name__,
                        "completed_steps": len(self.results)
                    }
                ))
            raise

    def _validate_inputs(self, inputs: Dict[str, Any]) -> None:
        """Validate that required flow inputs are provided."""
        for flow_input in self.spec.inputs:
            if flow_input.required and flow_input.name not in inputs:
                if flow_input.default is not None:
                    inputs[flow_input.name] = flow_input.default
                else:
                    raise FlowValidationError(
                        f"Required input '{flow_input.name}' is missing"
                    )


def load_flow(flow_path: Union[str, Path]) -> FlowSpec:
    """Load and validate flow YAML file."""
    logger.debug(f"Loading flow from: {flow_path}")
    
    flow_path = Path(flow_path)
    if not flow_path.exists():
        raise FlowValidationError(f"Flow file not found: {flow_path}")
    
    try:
        with open(flow_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise FlowValidationError(f"Invalid YAML in flow file: {e}")
    
    return _parse_flow_data(data, flow_path)


def _parse_flow_data(data: Dict[str, Any], source_path: Path) -> FlowSpec:
    """Parse flow data dictionary into FlowSpec."""
    try:
        # Parse inputs
        inputs = []
        for input_data in data.get('inputs', []):
            inputs.append(FlowInput(
                name=input_data['name'],
                type=input_data.get('type', 'string'),
                description=input_data.get('description', ''),
                required=input_data.get('required', True),
                default=input_data.get('default')
            ))
        
        # Parse outputs
        outputs = []
        for output_data in data.get('outputs', []):
            outputs.append(FlowOutput(
                name=output_data['name'],
                source=output_data['source'],
                description=output_data.get('description', '')
            ))
        
        # Parse steps
        steps = {}
        for step_name, step_data in data.get('steps', {}).items():
            prompt_name = step_data.get('prompt')
            skill_name = step_data.get('skill')

            if not prompt_name and not skill_name:
                raise FlowValidationError(
                    f"Step '{step_name}' must have either a 'prompt' or a 'skill' key"
                )
            if prompt_name and skill_name:
                raise FlowValidationError(
                    f"Step '{step_name}' cannot have both 'prompt' and 'skill' keys"
                )

            steps[step_name] = FlowStep(
                name=step_name,
                prompt_name=prompt_name,
                skill_name=skill_name,
                inputs=step_data.get('inputs', {}),
                outputs=step_data.get('outputs', []),
                depends_on=step_data.get('depends_on', []),
                when=step_data.get('when')
            )
        
        return FlowSpec(
            name=data.get('name', source_path.stem),
            description=data.get('description', ''),
            inputs=inputs,
            outputs=outputs,
            steps=steps
        )
        
    except KeyError as e:
        raise FlowValidationError(f"Missing required field in flow: {e}")
    except Exception as e:
        raise FlowValidationError(f"Failed to parse flow: {e}")


def list_flows(flows_dir: Union[str, Path]) -> List[Dict[str, str]]:
    """List available flows in the flows directory."""
    flows_dir = Path(flows_dir)
    flows = []
    
    if not flows_dir.exists():
        return flows
    
    for yaml_file in flows_dir.glob("*.yaml"):
        try:
            spec = load_flow(yaml_file)
            flows.append({
                'name': yaml_file.stem,
                'description': spec.description,
                'path': str(yaml_file)
            })
        except Exception as e:
            logger.warning(f"Failed to load flow {yaml_file}: {e}")
    
    return flows
