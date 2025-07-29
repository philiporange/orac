"""
Workflow engine for Orac - enables chaining multiple prompts in a DAG structure.

This module provides classes and functions for:
- Loading and validating workflow YAML specifications
- Building dependency graphs from workflow definitions
- Executing workflows with proper step ordering and result passing
- Template variable resolution for dynamic input mapping
"""

import re
import yaml
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Set, Union
from pathlib import Path
import networkx as nx

from .logger import logger
from .orac import Orac
from .progress import ProgressCallback, ProgressEvent, ProgressType


@dataclass
class WorkflowInput:
    """Represents a workflow input parameter."""
    name: str
    type: str = "string"
    description: str = ""
    required: bool = True
    default: Any = None


@dataclass
class WorkflowOutput:
    """Represents a workflow output mapping."""
    name: str
    source: str  # Format: "step_name.output_name"
    description: str = ""


@dataclass
class WorkflowStep:
    """Represents a single step in a workflow."""
    name: str
    prompt_name: str
    inputs: Dict[str, str]  # Maps param_name -> template string
    outputs: List[str]
    depends_on: List[str] = field(default_factory=list)
    when: Optional[str] = None  # Conditional execution (future feature)


@dataclass
class WorkflowSpec:
    """Complete workflow specification loaded from YAML."""
    name: str
    description: str
    inputs: List[WorkflowInput]
    outputs: List[WorkflowOutput]
    steps: Dict[str, WorkflowStep]


class WorkflowValidationError(Exception):
    """Raised when workflow validation fails."""
    pass


class WorkflowExecutionError(Exception):
    """Raised when workflow execution fails."""
    pass


class WorkflowEngine:
    """Executes workflows by managing step dependencies and data flow."""

    def __init__(self, workflow_spec: WorkflowSpec, prompts_dir: str = "prompts", 
                 progress_callback: Optional[ProgressCallback] = None):
        self.spec = workflow_spec
        self.prompts_dir = prompts_dir
        self.progress_callback = progress_callback
        self.results: Dict[str, Dict[str, Any]] = {}
        self.graph = self._build_dependency_graph()
        self.execution_order = self._get_execution_order()

    def _build_dependency_graph(self) -> nx.DiGraph:
        """Build DAG from step dependencies and data flow."""
        logger.debug(f"Building dependency graph for workflow: {self.spec.name}")
        graph = nx.DiGraph()
        
        # Add all steps as nodes
        for step_name in self.spec.steps:
            graph.add_node(step_name)
        
        # Add explicit dependencies
        for step_name, step in self.spec.steps.items():
            for dep in step.depends_on:
                if dep not in self.spec.steps:
                    raise WorkflowValidationError(
                        f"Step '{step_name}' depends on unknown step '{dep}'"
                    )
                graph.add_edge(dep, step_name)
        
        # Add implicit dependencies from data flow
        for step_name, step in self.spec.steps.items():
            for input_template in step.inputs.values():
                referenced_steps = self._extract_step_references(input_template)
                for ref_step in referenced_steps:
                    if ref_step not in self.spec.steps:
                        raise WorkflowValidationError(
                            f"Step '{step_name}' references unknown step '{ref_step}'"
                        )
                    if not graph.has_edge(ref_step, step_name):
                        graph.add_edge(ref_step, step_name)
        
        # Check for cycles
        if not nx.is_directed_acyclic_graph(graph):
            raise WorkflowValidationError("Workflow contains dependency cycles")
        
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
            raise WorkflowValidationError(f"Failed to determine execution order: {e}")

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
                raise WorkflowExecutionError(
                    f"Failed to resolve template variable '{var_path}': {e}"
                )
        
        pattern = r'\$\{([^}]+)\}'
        resolved = re.sub(pattern, replace_var, template)
        logger.debug(f"Resolved to: {resolved}")
        return resolved

    def _build_context(self, workflow_inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Build context for template resolution."""
        context = {
            'inputs': workflow_inputs,
        }
        
        # Add step results
        for step_name, step_results in self.results.items():
            context[step_name] = step_results
        
        return context

    def _execute_step(self, step_name: str, context: Dict[str, Any], step_index: int = 0, total_steps: int = 0) -> Dict[str, Any]:
        """Execute a single workflow step."""
        logger.info(f"Executing workflow step: {step_name}")
        step = self.spec.steps[step_name]
        
        # Emit step start progress
        if self.progress_callback:
            self.progress_callback(ProgressEvent(
                type=ProgressType.WORKFLOW_STEP_START,
                message=f"Executing step: {step_name}",
                current_step=step_index + 1,
                total_steps=total_steps,
                step_name=step_name,
                metadata={"step_name": step_name, "prompt_name": step.prompt_name}
            ))
        
        # Resolve input templates
        resolved_inputs = {}
        for param_name, template in step.inputs.items():
            resolved_inputs[param_name] = self._resolve_template(template, context)
        
        logger.debug(f"Step '{step_name}' resolved inputs: {resolved_inputs}")
        
        # Execute the prompt
        try:
            # Pass progress callback to Orac instance
            orac = Orac(step.prompt_name, prompts_dir=self.prompts_dir,
                       progress_callback=self.progress_callback)
            result = orac(**resolved_inputs)
            
            # Handle different result types
            if isinstance(result, dict):
                step_results = result
            else:
                # For string results, create a dict with the first output name
                if step.outputs:
                    step_results = {step.outputs[0]: result}
                else:
                    step_results = {'result': result}
            
            logger.debug(f"Step '{step_name}' results: {step_results}")
            
            # Emit step completion progress
            if self.progress_callback:
                self.progress_callback(ProgressEvent(
                    type=ProgressType.WORKFLOW_STEP_COMPLETE,
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
                    type=ProgressType.WORKFLOW_ERROR,
                    message=f"Step '{step_name}' failed: {str(e)}",
                    current_step=step_index + 1,
                    total_steps=total_steps,
                    step_name=step_name,
                    metadata={"step_name": step_name, "error_type": type(e).__name__}
                ))
            raise WorkflowExecutionError(f"Step '{step_name}' failed: {e}")

    def execute(self, inputs: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
        """Execute the workflow and return final outputs."""
        logger.info(f"Starting workflow execution: {self.spec.name}")
        
        # Emit workflow start progress
        if self.progress_callback:
            self.progress_callback(ProgressEvent(
                type=ProgressType.WORKFLOW_START,
                message=f"Starting workflow: {self.spec.name}",
                total_steps=len(self.execution_order),
                metadata={
                    "workflow_name": self.spec.name,
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
                        raise WorkflowExecutionError(
                            f"Invalid output source format '{output.source}'. Expected 'step.output'"
                        )
                    
                    step_name, output_name = parts
                    if step_name not in self.results:
                        raise WorkflowExecutionError(f"Output references unknown step '{step_name}'")
                    
                    if output_name not in self.results[step_name]:
                        raise WorkflowExecutionError(
                            f"Output '{output_name}' not found in step '{step_name}' results"
                        )
                    
                    final_outputs[output.name] = self.results[step_name][output_name]
                    
                except Exception as e:
                    raise WorkflowExecutionError(f"Failed to resolve output '{output.name}': {e}")
            
            logger.info(f"Workflow completed successfully with {len(final_outputs)} outputs")
            
            # Emit workflow completion progress
            if self.progress_callback:
                self.progress_callback(ProgressEvent(
                    type=ProgressType.WORKFLOW_COMPLETE,
                    message=f"Completed workflow: {self.spec.name}",
                    current_step=len(self.execution_order),
                    total_steps=len(self.execution_order),
                    metadata={
                        "workflow_name": self.spec.name,
                        "outputs": list(final_outputs.keys()),
                        "total_steps_completed": len(self.execution_order)
                    }
                ))
            
            return final_outputs
            
        except Exception as e:
            # Emit workflow error progress
            if self.progress_callback:
                self.progress_callback(ProgressEvent(
                    type=ProgressType.WORKFLOW_ERROR,
                    message=f"Workflow '{self.spec.name}' failed: {str(e)}",
                    metadata={
                        "workflow_name": self.spec.name,
                        "error_type": type(e).__name__,
                        "completed_steps": len(self.results)
                    }
                ))
            raise

    def _validate_inputs(self, inputs: Dict[str, Any]) -> None:
        """Validate that required workflow inputs are provided."""
        for workflow_input in self.spec.inputs:
            if workflow_input.required and workflow_input.name not in inputs:
                if workflow_input.default is not None:
                    inputs[workflow_input.name] = workflow_input.default
                else:
                    raise WorkflowValidationError(
                        f"Required input '{workflow_input.name}' is missing"
                    )


def load_workflow(workflow_path: Union[str, Path]) -> WorkflowSpec:
    """Load and validate workflow YAML file."""
    logger.debug(f"Loading workflow from: {workflow_path}")
    
    workflow_path = Path(workflow_path)
    if not workflow_path.exists():
        raise WorkflowValidationError(f"Workflow file not found: {workflow_path}")
    
    try:
        with open(workflow_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise WorkflowValidationError(f"Invalid YAML in workflow file: {e}")
    
    return _parse_workflow_data(data, workflow_path)


def _parse_workflow_data(data: Dict[str, Any], source_path: Path) -> WorkflowSpec:
    """Parse workflow data dictionary into WorkflowSpec."""
    try:
        # Parse inputs
        inputs = []
        for input_data in data.get('inputs', []):
            inputs.append(WorkflowInput(
                name=input_data['name'],
                type=input_data.get('type', 'string'),
                description=input_data.get('description', ''),
                required=input_data.get('required', True),
                default=input_data.get('default')
            ))
        
        # Parse outputs
        outputs = []
        for output_data in data.get('outputs', []):
            outputs.append(WorkflowOutput(
                name=output_data['name'],
                source=output_data['source'],
                description=output_data.get('description', '')
            ))
        
        # Parse steps
        steps = {}
        for step_name, step_data in data.get('steps', {}).items():
            steps[step_name] = WorkflowStep(
                name=step_name,
                prompt_name=step_data['prompt'],
                inputs=step_data.get('inputs', {}),
                outputs=step_data.get('outputs', []),
                depends_on=step_data.get('depends_on', []),
                when=step_data.get('when')
            )
        
        return WorkflowSpec(
            name=data.get('name', source_path.stem),
            description=data.get('description', ''),
            inputs=inputs,
            outputs=outputs,
            steps=steps
        )
        
    except KeyError as e:
        raise WorkflowValidationError(f"Missing required field in workflow: {e}")
    except Exception as e:
        raise WorkflowValidationError(f"Failed to parse workflow: {e}")


def list_workflows(workflows_dir: Union[str, Path]) -> List[Dict[str, str]]:
    """List available workflows in the workflows directory."""
    workflows_dir = Path(workflows_dir)
    workflows = []
    
    if not workflows_dir.exists():
        return workflows
    
    for yaml_file in workflows_dir.glob("*.yaml"):
        try:
            spec = load_workflow(yaml_file)
            workflows.append({
                'name': yaml_file.stem,
                'description': spec.description,
                'path': str(yaml_file)
            })
        except Exception as e:
            logger.warning(f"Failed to load workflow {yaml_file}: {e}")
    
    return workflows