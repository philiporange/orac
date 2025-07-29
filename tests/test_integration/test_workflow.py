"""
Workflow integration tests for essential functionality.

These tests focus on the core workflow features:
- Basic workflow loading
- Simple workflow execution
- Input/output handling
- Error handling
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from orac.workflow import WorkflowEngine, load_workflow, list_workflows
from orac.workflow import WorkflowValidationError, WorkflowExecutionError


class TestWorkflow:
    """Tests for core workflow functionality."""

    @pytest.mark.integration
    def test_workflow_loading(self, temp_dir):
        """Test basic workflow loading from YAML."""
        workflows_dir = temp_dir / "workflows"
        workflows_dir.mkdir()
        
        # Create a simple workflow
        (workflows_dir / "simple.yaml").write_text("""
name: "Simple Test Workflow"
description: "A minimal test workflow"

inputs:
  - name: input_text
    type: string
    description: "Text to process"
    required: true

outputs:
  - name: result
    source: process_step.output
    description: "Processed result"

steps:
  process_step:
    prompt: test_prompt
    inputs:
      text: ${inputs.input_text}
    outputs:
      - output
""")
        
        # Should load without error
        workflow_path = workflows_dir / "simple.yaml"
        workflow = load_workflow(str(workflow_path))
        assert workflow.name == "Simple Test Workflow"
        assert len(workflow.inputs) == 1
        assert len(workflow.outputs) == 1
        assert len(workflow.steps) == 1

    @pytest.mark.integration
    def test_workflow_list(self, temp_dir):
        """Test listing available workflows."""
        workflows_dir = temp_dir / "workflows"
        workflows_dir.mkdir()
        
        # Create test workflows
        (workflows_dir / "workflow1.yaml").write_text("""
name: "Workflow 1"
steps:
  step1:
    prompt: test
""")
        
        (workflows_dir / "workflow2.yaml").write_text("""
name: "Workflow 2" 
steps:
  step1:
    prompt: test
""")
        
        workflows = list_workflows(str(workflows_dir))
        assert len(workflows) >= 2
        
        # Should contain our test workflow files
        workflow_names = [w['name'] for w in workflows] 
        # The function returns filename without extension, not the name field
        assert "workflow1" in workflow_names
        assert "workflow2" in workflow_names

    @pytest.mark.integration
    @patch('orac.orac.call_api')
    def test_simple_workflow_execution(self, mock_call_api, temp_dir, test_prompts_dir):
        """Test execution of a simple single-step workflow."""
        mock_call_api.return_value = "Processed: Hello World"
        
        workflows_dir = temp_dir / "workflows"
        workflows_dir.mkdir()
        
        # Create workflow
        (workflows_dir / "simple_exec.yaml").write_text("""
name: "Simple Execution Test"
description: "Test single step execution"

inputs:
  - name: message
    type: string
    required: true

outputs:
  - name: result
    source: process.output

steps:
  process:
    prompt: test_prompt
    inputs:
      param: ${inputs.message}
    outputs:
      - output
""")
        
        # Load and execute workflow
        workflow = load_workflow(str(workflows_dir / "simple_exec.yaml"))
        engine = WorkflowEngine(workflow, prompts_dir=str(test_prompts_dir))
        
        results = engine.execute(inputs={"message": "Hello World"})
        
        # Should have executed successfully
        assert "result" in results
        assert results["result"] == "Processed: Hello World"
        
        # Should have called the API
        mock_call_api.assert_called_once()



    @pytest.mark.integration
    @patch('orac.orac.call_api')
    def test_workflow_execution_error(self, mock_call_api, temp_dir, test_prompts_dir):
        """Test workflow execution error handling."""
        # Mock API call to raise an exception
        mock_call_api.side_effect = Exception("API Error")
        
        workflows_dir = temp_dir / "workflows"
        workflows_dir.mkdir()
        
        (workflows_dir / "error_test.yaml").write_text("""
name: "Error Test Workflow"
inputs:
  - name: input
    type: string
    required: true
outputs:
  - name: result
    source: step1.output
steps:
  step1:
    prompt: test_prompt
    inputs:
      param: ${inputs.input}
    outputs:
      - output
""")
        
        workflow = load_workflow(str(workflows_dir / "error_test.yaml"))
        engine = WorkflowEngine(workflow, prompts_dir=str(test_prompts_dir))
        
        with pytest.raises(WorkflowExecutionError):
            engine.execute(inputs={"input": "test"})



class TestWorkflowInputOutput:
    """Tests for workflow input/output handling."""


    @pytest.mark.integration
    @patch('orac.orac.call_api')
    def test_output_mapping(self, mock_call_api, temp_dir, test_prompts_dir):
        """Test workflow output mapping from step results."""
        mock_call_api.return_value = "Step Output"
        
        workflows_dir = temp_dir / "workflows"
        workflows_dir.mkdir()
        
        (workflows_dir / "output_test.yaml").write_text("""
name: "Output Mapping Test"
inputs:
  - name: input
    type: string
    required: true

outputs:
  - name: direct_output
    source: step1.result
  - name: transformed_output  
    source: step1.result
    description: "Same output with different name"

steps:
  step1:
    prompt: test_prompt
    inputs:
      param: ${inputs.input}
    outputs:
      - result
""")
        
        workflow = load_workflow(str(workflows_dir / "output_test.yaml"))
        engine = WorkflowEngine(workflow, prompts_dir=str(test_prompts_dir))
        
        results = engine.execute(inputs={"input": "test"})
        
        # Should map outputs correctly
        assert "direct_output" in results
        assert "transformed_output" in results
        assert results["direct_output"] == "Step Output"
        assert results["transformed_output"] == "Step Output"