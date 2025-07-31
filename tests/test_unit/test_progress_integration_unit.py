"""
Unit tests for progress tracking integration with Prompt and Flow.

These tests focus on testing the progress callback integration without
requiring actual API calls or file system operations.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock, call
from pathlib import Path

from orac.progress import ProgressEvent, ProgressType, ProgressTracker
from orac.prompt import Prompt
from orac.flow import Flow, FlowSpec, FlowStep, FlowInput, FlowOutput


class TestPromptProgressIntegrationUnit:
    """Unit tests for progress tracking in Prompt class."""
    
    @pytest.mark.unit
    def test_prompt_progress_callback_parameter(self, test_prompts_dir):
        """Test that Prompt accepts progress_callback parameter."""
        mock_callback = Mock()
        
        prompt = Prompt(
            "test_prompt", 
            prompts_dir=str(test_prompts_dir),
            progress_callback=mock_callback
        )
        
        assert prompt.progress_callback == mock_callback
    
    @pytest.mark.unit
    def test_prompt_progress_callback_none_by_default(self, test_prompts_dir):
        """Test that progress_callback defaults to None."""
        prompt = Prompt("test_prompt", prompts_dir=str(test_prompts_dir))
        
        assert prompt.progress_callback is None
    
    @pytest.mark.unit
    @patch('orac.prompt.call_api')
    def test_prompt_progress_events_emitted(self, mock_call_api, test_prompts_dir):
        """Test that Prompt emits progress events during completion."""
        mock_call_api.return_value = "Test response"
        mock_callback = Mock()
        
        prompt = Prompt(
            "test_prompt", 
            prompts_dir=str(test_prompts_dir),
            progress_callback=mock_callback
        )
        
        result = prompt.completion()
        
        # Verify result
        assert result == "Test response"
        
        # Verify progress events were emitted
        assert mock_callback.call_count >= 3  # At least START, API_START, API_COMPLETE, COMPLETE
        
        # Check the specific events
        calls = mock_callback.call_args_list
        events = [call[0][0] for call in calls]
        
        # Find specific event types
        start_events = [e for e in events if e.type == ProgressType.PROMPT_START]
        complete_events = [e for e in events if e.type == ProgressType.PROMPT_COMPLETE] 
        api_start_events = [e for e in events if e.type == ProgressType.API_REQUEST_START]
        api_complete_events = [e for e in events if e.type == ProgressType.API_REQUEST_COMPLETE]
        
        assert len(start_events) == 1
        assert len(complete_events) == 1
        assert len(api_start_events) == 1
        assert len(api_complete_events) == 1
        
        # Verify event content
        start_event = start_events[0]
        assert "test_prompt" in start_event.message
        assert start_event.metadata["prompt_name"] == "test_prompt"
        
        complete_event = complete_events[0]
        assert "test_prompt" in complete_event.message
        assert complete_event.metadata["prompt_name"] == "test_prompt"
    
    @pytest.mark.unit
    @patch('orac.prompt.call_api')
    def test_prompt_progress_error_handling(self, mock_call_api, test_prompts_dir):
        """Test that Prompt emits error events when completion fails."""
        mock_call_api.side_effect = RuntimeError("API failed")
        mock_callback = Mock()
        
        prompt = Prompt(
            "test_prompt", 
            prompts_dir=str(test_prompts_dir),
            progress_callback=mock_callback
        )
        
        with pytest.raises(RuntimeError, match="API failed"):
            prompt.completion()
        
        # Verify error event was emitted
        calls = mock_callback.call_args_list
        events = [call[0][0] for call in calls]
        
        error_events = [e for e in events if e.type == ProgressType.PROMPT_ERROR]
        assert len(error_events) == 1
        
        error_event = error_events[0]
        assert "test_prompt" in error_event.message
        assert "API failed" in error_event.message
        assert error_event.metadata["error_type"] == "RuntimeError"
    
    @pytest.mark.unit
    @patch('orac.prompt.call_api')
    def test_prompt_no_progress_callback_works_normally(self, mock_call_api, test_prompts_dir):
        """Test that Prompt works normally without progress callback."""
        mock_call_api.return_value = "Test response"
        
        prompt = Prompt("test_prompt", prompts_dir=str(test_prompts_dir))
        
        result = prompt.completion()
        
        assert result == "Test response"
        mock_call_api.assert_called_once()
        # No exceptions should be raised
    
    @pytest.mark.unit
    @patch('orac.prompt.call_api')
    def test_prompt_progress_metadata_includes_parameters(self, mock_call_api, test_prompts_dir):
        """Test that progress events include parameter metadata."""
        mock_call_api.return_value = "Test response"
        mock_callback = Mock()
        
        prompt = Prompt(
            "test_prompt", 
            prompts_dir=str(test_prompts_dir),
            progress_callback=mock_callback
        )
        
        # Call with parameters
        result = prompt.completion(test_param="test_value", another_param=42)
        
        # Check start event includes parameters
        calls = mock_callback.call_args_list
        start_event = calls[0][0][0]  # First call, first arg, the event
        
        assert start_event.type == ProgressType.PROMPT_START
        assert "params" in start_event.metadata
        assert start_event.metadata["params"]["test_param"] == "test_value"
        assert start_event.metadata["params"]["another_param"] == 42


class TestFlowProgressUnit:
    """Unit tests for progress tracking in Flow."""
    
    def create_test_flow_spec(self):
        """Create a simple test flow spec."""
        return FlowSpec(
            name="test_flow",
            description="Test flow",
            inputs=[
                FlowInput(name="input1", type="string", required=True)
            ],
            outputs=[
                FlowOutput(name="output1", source="step1.result")
            ],
            steps={
                "step1": FlowStep(
                    name="step1",
                    prompt_name="test_prompt",
                    inputs={"param1": "${inputs.input1}"},
                    outputs=["result"]
                )
            }
        )
    
    @pytest.mark.unit
    def test_flow_engine_progress_callback_parameter(self):
        """Test that Flow accepts progress_callback parameter."""
        spec = self.create_test_flow_spec()
        mock_callback = Mock()
        
        engine = Flow(spec, progress_callback=mock_callback)
        
        assert engine.progress_callback == mock_callback
    
    @pytest.mark.unit
    def test_flow_engine_progress_callback_none_by_default(self):
        """Test that progress_callback defaults to None."""
        spec = self.create_test_flow_spec()
        
        engine = Flow(spec)
        
        assert engine.progress_callback is None
    
    @pytest.mark.unit
    @patch('orac.flow.Prompt')
    def test_flow_engine_progress_events_dry_run(self, mock_prompt_class):
        """Test flow progress events in dry run mode."""
        spec = self.create_test_flow_spec()
        mock_callback = Mock()
        
        engine = Flow(spec, progress_callback=mock_callback)
        
        # Dry run should only emit start event
        result = engine.execute({"input1": "test"}, dry_run=True)
        
        assert result == {}
        
        # Should emit flow start event
        mock_callback.assert_called_once()
        event = mock_callback.call_args[0][0]
        assert event.type == ProgressType.FLOW_START
        assert "test_flow" in event.message
        assert event.total_steps == 1
        assert event.metadata["dry_run"] is True
    
    @pytest.mark.unit
    @patch('orac.flow.Prompt')
    def test_flow_engine_progress_events_full_flow(self, mock_prompt_class):
        """Test flow progress events for full execution."""
        spec = self.create_test_flow_spec()
        mock_callback = Mock()
        
        # Mock Prompt instance
        mock_prompt_instance = Mock()
        mock_prompt_instance.return_value = "step1_result"
        mock_prompt_class.return_value = mock_prompt_instance
        
        engine = Flow(spec, progress_callback=mock_callback)
        
        result = engine.execute({"input1": "test_input"})
        
        # Verify result
        assert result == {"output1": "step1_result"}
        
        # Verify progress events were emitted
        calls = mock_callback.call_args_list
        events = [call[0][0] for call in calls]
        
        # Should have: flow_start, step_start, step_complete, flow_complete
        event_types = [e.type for e in events]
        
        assert ProgressType.FLOW_START in event_types
        assert ProgressType.FLOW_STEP_START in event_types
        assert ProgressType.FLOW_STEP_COMPLETE in event_types
        assert ProgressType.FLOW_COMPLETE in event_types
        
        # Check flow start event
        start_events = [e for e in events if e.type == ProgressType.FLOW_START]
        assert len(start_events) == 1
        start_event = start_events[0]
        assert start_event.total_steps == 1
        assert start_event.metadata["flow_name"] == "test_flow"
        
        # Check step start event
        step_start_events = [e for e in events if e.type == ProgressType.FLOW_STEP_START]
        assert len(step_start_events) == 1
        step_start_event = step_start_events[0]
        assert step_start_event.current_step == 1
        assert step_start_event.total_steps == 1
        assert step_start_event.step_name == "step1"
        
        # Check step complete event
        step_complete_events = [e for e in events if e.type == ProgressType.FLOW_STEP_COMPLETE]
        assert len(step_complete_events) == 1
        step_complete_event = step_complete_events[0]
        assert step_complete_event.step_name == "step1"
        
        # Check flow complete event
        complete_events = [e for e in events if e.type == ProgressType.FLOW_COMPLETE]
        assert len(complete_events) == 1
        complete_event = complete_events[0]
        assert complete_event.metadata["flow_name"] == "test_flow"
    
    @pytest.mark.unit
    @patch('orac.flow.Prompt')
    def test_flow_engine_progress_error_handling(self, mock_prompt_class):
        """Test flow progress error handling."""
        spec = self.create_test_flow_spec()
        mock_callback = Mock()
        
        # Mock Prompt to raise an exception
        mock_prompt_instance = Mock()
        mock_prompt_instance.side_effect = RuntimeError("Step failed")
        mock_prompt_class.return_value = mock_prompt_instance
        
        engine = Flow(spec, progress_callback=mock_callback)
        
        with pytest.raises(Exception):  # FlowExecutionError wraps the RuntimeError
            engine.execute({"input1": "test_input"})
        
        # Verify error events were emitted (step error + flow error)
        calls = mock_callback.call_args_list
        events = [call[0][0] for call in calls]
        
        error_events = [e for e in events if e.type == ProgressType.FLOW_ERROR]
        assert len(error_events) >= 1  # At least one error event
        
        # First error should be the step error
        step_error = error_events[0]
        assert "step1" in step_error.message
        assert "failed" in step_error.message.lower()
        assert step_error.step_name == "step1"
    
    @pytest.mark.unit
    @patch('orac.flow.Prompt')
    def test_flow_engine_passes_progress_callback_to_orac(self, mock_prompt_class):
        """Test that Flow passes progress callback to Prompt instances."""
        spec = self.create_test_flow_spec()
        mock_callback = Mock()
        
        mock_prompt_instance = Mock()
        mock_prompt_instance.return_value = "result"
        mock_prompt_class.return_value = mock_prompt_instance
        
        engine = Flow(spec, progress_callback=mock_callback)
        engine.execute({"input1": "test"})
        
        # Verify Prompt was created with progress callback
        mock_prompt_class.assert_called_once()
        call_args = mock_prompt_class.call_args
        
        # Check that progress_callback was passed
        assert 'progress_callback' in call_args.kwargs
        assert call_args.kwargs['progress_callback'] == mock_callback
    
    @pytest.mark.unit
    @patch('orac.flow.Prompt')
    def test_flow_engine_multi_step_progress(self, mock_prompt_class):
        """Test progress tracking for multi-step flow."""
        # Create multi-step flow
        spec = FlowSpec(
            name="multi_step_flow",
            description="Multi-step test",
            inputs=[FlowInput(name="input1", type="string", required=True)],
            outputs=[FlowOutput(name="final_output", source="step2.result")],
            steps={
                "step1": FlowStep(
                    name="step1",
                    prompt_name="prompt1", 
                    inputs={"param": "${inputs.input1}"},
                    outputs=["result"]
                ),
                "step2": FlowStep(
                    name="step2",
                    prompt_name="prompt2",
                    inputs={"param": "${step1.result}"},
                    outputs=["result"],
                    depends_on=["step1"]
                )
            }
        )
        
        mock_callback = Mock()
        
        # Mock Prompt instances
        mock_prompt_instance = Mock()
        mock_prompt_instance.side_effect = ["step1_result", "step2_result"]
        mock_prompt_class.return_value = mock_prompt_instance
        
        engine = Flow(spec, progress_callback=mock_callback)
        result = engine.execute({"input1": "test"})
        
        assert result == {"final_output": "step2_result"}
        
        # Verify step events for both steps
        calls = mock_callback.call_args_list
        events = [call[0][0] for call in calls]
        
        step_start_events = [e for e in events if e.type == ProgressType.FLOW_STEP_START]
        step_complete_events = [e for e in events if e.type == ProgressType.FLOW_STEP_COMPLETE]
        
        assert len(step_start_events) == 2
        assert len(step_complete_events) == 2
        
        # Check step progression
        assert step_start_events[0].current_step == 1
        assert step_start_events[0].total_steps == 2
        assert step_start_events[0].step_name == "step1"
        
        assert step_start_events[1].current_step == 2
        assert step_start_events[1].total_steps == 2
        assert step_start_events[1].step_name == "step2"


class TestProgressCallbackInterfaceUnit:
    """Unit tests for progress callback interface compliance."""
    
    @pytest.mark.unit
    def test_progress_callback_signature(self):
        """Test that progress callback has correct signature."""
        def valid_callback(event: ProgressEvent) -> None:
            pass
        
        # Should accept ProgressEvent and return None
        event = ProgressEvent(ProgressType.PROMPT_START, "Test")
        result = valid_callback(event)
        assert result is None
    
    @pytest.mark.unit
    def test_progress_tracker_as_callback(self):
        """Test that ProgressTracker.track can be used as callback."""
        tracker = ProgressTracker()
        
        # Should work as a callback
        event = ProgressEvent(ProgressType.FLOW_START, "Starting")
        tracker.track(event)
        
        assert len(tracker.events) == 1
        assert tracker.events[0] == event
    
    @pytest.mark.unit
    def test_lambda_callback(self):
        """Test that lambda functions work as callbacks."""
        events = []
        callback = lambda event: events.append(event)
        
        event = ProgressEvent(ProgressType.PROMPT_COMPLETE, "Done")
        callback(event)
        
        assert len(events) == 1
        assert events[0] == event
    
    @pytest.mark.unit
    def test_mock_callback_compatibility(self):
        """Test that Mock objects work as callbacks."""
        mock_callback = Mock()
        
        event = ProgressEvent(ProgressType.API_REQUEST_START, "API call")
        mock_callback(event)
        
        mock_callback.assert_called_once_with(event)


class TestProgressMetadataUnit:
    """Unit tests for progress event metadata handling."""
    
    @pytest.mark.unit
    def test_metadata_extensibility(self):
        """Test that metadata can be extended for different use cases."""
        # Different metadata structures should work
        prompt_metadata = {
            "prompt_name": "test",
            "model_name": "gpt-4",
            "parameters": {"country": "France"},
            "file_count": 0
        }
        
        flow_metadata = {
            "flow_name": "data_analysis",
            "step_name": "preprocessing",
            "step_index": 1,
            "total_steps": 5,
            "execution_order": ["load", "preprocess", "analyze", "report"],
            "dependencies": ["load"]
        }
        
        api_metadata = {
            "endpoint": "https://api.openai.com/v1/chat/completions",
            "model": "gpt-4",
            "tokens_estimated": 150,
            "files_uploaded": ["data.csv", "config.json"],
            "request_id": "req_12345"
        }
        
        events = [
            ProgressEvent(ProgressType.PROMPT_START, "Test", metadata=prompt_metadata),
            ProgressEvent(ProgressType.FLOW_STEP_START, "Test", metadata=flow_metadata),
            ProgressEvent(ProgressType.API_REQUEST_START, "Test", metadata=api_metadata)
        ]
        
        # All should serialize properly
        for event in events:
            event_dict = event.to_dict()
            assert "metadata" in event_dict
            assert isinstance(event_dict["metadata"], dict)
            assert len(event_dict["metadata"]) > 0
    
    @pytest.mark.unit
    def test_metadata_none_handling(self):
        """Test that None metadata is handled properly."""
        event = ProgressEvent(ProgressType.PROMPT_START, "Test", metadata=None)
        
        assert event.metadata is None
        
        event_dict = event.to_dict()
        assert event_dict["metadata"] == {}  # Should default to empty dict in serialization
    
    @pytest.mark.unit
    def test_metadata_empty_dict(self):
        """Test that empty metadata dict is handled properly."""
        event = ProgressEvent(ProgressType.PROMPT_START, "Test", metadata={})
        
        assert event.metadata == {}
        
        event_dict = event.to_dict()
        assert event_dict["metadata"] == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])