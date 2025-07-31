"""
Flow integration tests for essential functionality.

These tests focus on the core flow features:
- Basic flow loading
- Simple flow execution
- Input/output handling
- Error handling
"""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from orac.flow import Flow, load_flow, list_flows
from orac.flow import FlowValidationError, FlowExecutionError


class TestFlow:
    """Tests for core flow functionality."""

    @pytest.mark.integration
    def test_flow_loading(self, temp_dir):
        """Test basic flow loading from YAML."""
        flows_dir = temp_dir / "flows"
        flows_dir.mkdir()
        
        # Create a simple flow
        (flows_dir / "simple.yaml").write_text("""
name: "Simple Test Flow"
description: "A minimal test flow"

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
        flow_path = flows_dir / "simple.yaml"
        flow = load_flow(str(flow_path))
        assert flow.name == "Simple Test Flow"
        assert len(flow.inputs) == 1
        assert len(flow.outputs) == 1
        assert len(flow.steps) == 1

    @pytest.mark.integration
    def test_flow_list(self, temp_dir):
        """Test listing available flows."""
        flows_dir = temp_dir / "flows"
        flows_dir.mkdir()
        
        # Create test flows
        (flows_dir / "flow1.yaml").write_text("""
name: "Flow 1"
steps:
  step1:
    prompt: test
""")
        
        (flows_dir / "flow2.yaml").write_text("""
name: "Flow 2" 
steps:
  step1:
    prompt: test
""")
        
        flows = list_flows(str(flows_dir))
        assert len(flows) >= 2
        
        # Should contain our test flow files
        flow_names = [w['name'] for w in flows] 
        # The function returns filename without extension, not the name field
        assert "flow1" in flow_names
        assert "flow2" in flow_names

    @pytest.mark.integration
    @patch('orac.prompt.call_api')
    def test_simple_flow_execution(self, mock_call_api, temp_dir, test_prompts_dir):
        """Test execution of a simple single-step flow."""
        mock_call_api.return_value = "Processed: Hello World"
        
        flows_dir = temp_dir / "flows"
        flows_dir.mkdir()
        
        # Create flow
        (flows_dir / "simple_exec.yaml").write_text("""
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
        
        # Load and execute flow
        flow = load_flow(str(flows_dir / "simple_exec.yaml"))
        engine = Flow(flow, prompts_dir=str(test_prompts_dir))
        
        results = engine.execute(inputs={"message": "Hello World"})
        
        # Should have executed successfully
        assert "result" in results
        assert results["result"] == "Processed: Hello World"
        
        # Should have called the API
        mock_call_api.assert_called_once()



    @pytest.mark.integration
    @patch('orac.prompt.call_api')
    def test_flow_execution_error(self, mock_call_api, temp_dir, test_prompts_dir):
        """Test flow execution error handling."""
        # Mock API call to raise an exception
        mock_call_api.side_effect = Exception("API Error")
        
        flows_dir = temp_dir / "flows"
        flows_dir.mkdir()
        
        (flows_dir / "error_test.yaml").write_text("""
name: "Error Test Flow"
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
        
        flow = load_flow(str(flows_dir / "error_test.yaml"))
        engine = Flow(flow, prompts_dir=str(test_prompts_dir))
        
        with pytest.raises(FlowExecutionError):
            engine.execute(inputs={"input": "test"})



    @pytest.mark.integration
    @patch('orac.prompt.call_api')
    def test_flow_with_skill_step(self, mock_call_api, temp_dir, test_prompts_dir, test_skills_dir):
        """Test a flow that includes a skill step."""
        mock_call_api.return_value = "Analyzed: 8.0"

        flows_dir = temp_dir / "flows"
        flows_dir.mkdir()

        (flows_dir / "skill_flow.yaml").write_text("""
name: "Skill Flow Test"
description: "A flow that uses a skill"

inputs:
  - name: expression
    type: string
    required: true

outputs:
  - name: final_result
    source: analyze_step.result

steps:
  calculate_step:
    skill: calculator
    inputs:
      expression: ${inputs.expression}

  analyze_step:
    prompt: test_prompt
    depends_on: [calculate_step]
    inputs:
      param: ${calculate_step.result}
    outputs:
      - result
""")

        flow = load_flow(str(flows_dir / "skill_flow.yaml"))
        engine = Flow(flow, prompts_dir=str(test_prompts_dir), skills_dir=str(test_skills_dir))

        results = engine.execute(inputs={"expression": "4 * 2"})

        assert "final_result" in results
        assert results["final_result"] == "Analyzed: 8.0"
        mock_call_api.assert_called_once()


class TestFlowInputOutput:
    """Tests for flow input/output handling."""


    @pytest.mark.integration
    @patch('orac.prompt.call_api')
    def test_output_mapping(self, mock_call_api, temp_dir, test_prompts_dir):
        """Test flow output mapping from step results."""
        mock_call_api.return_value = "Step Output"
        
        flows_dir = temp_dir / "flows"
        flows_dir.mkdir()
        
        (flows_dir / "output_test.yaml").write_text("""
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
        
        flow = load_flow(str(flows_dir / "output_test.yaml"))
        engine = Flow(flow, prompts_dir=str(test_prompts_dir))
        
        results = engine.execute(inputs={"input": "test"})
        
        # Should map outputs correctly
        assert "direct_output" in results
        assert "transformed_output" in results
        assert results["direct_output"] == "Step Output"
        assert results["transformed_output"] == "Step Output"