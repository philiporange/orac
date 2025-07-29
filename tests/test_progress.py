"""
Tests for progress tracking functionality.

This module tests the progress infrastructure including:
- Progress event creation and handling
- Progress callbacks in Orac class
- Progress tracking in flows 
- CLI progress reporting
"""
import pytest
import time
from datetime import datetime
from unittest.mock import Mock, call
from pathlib import Path

from orac.progress import (
    ProgressEvent, ProgressType, ProgressCallback, ProgressTracker,
    create_simple_callback
)
from orac.cli_progress import CLIProgressReporter, StreamingProgressReporter, create_cli_reporter
from orac.orac import Orac
from orac.flow import FlowEngine, FlowSpec, FlowStep, FlowInput, FlowOutput


class TestProgressEvent:
    """Test ProgressEvent class functionality."""
    
    def test_progress_event_creation(self):
        """Test basic ProgressEvent creation."""
        event = ProgressEvent(
            type=ProgressType.PROMPT_START,
            message="Starting test prompt",
            current_step=1,
            total_steps=3,
            step_name="test_step",
            metadata={"prompt_name": "test"}
        )
        
        assert event.type == ProgressType.PROMPT_START
        assert event.message == "Starting test prompt"
        assert event.current_step == 1
        assert event.total_steps == 3
        assert event.step_name == "test_step"
        assert event.metadata == {"prompt_name": "test"}
        assert event.timestamp is not None
        assert isinstance(event.timestamp, datetime)
    
    def test_progress_percentage_calculation(self):
        """Test progress percentage calculation."""
        event = ProgressEvent(
            type=ProgressType.FLOW_STEP_START,
            message="Test",
            current_step=2,
            total_steps=4
        )
        
        assert event.progress_percentage == 50.0
        
        # Test edge cases
        event_no_steps = ProgressEvent(
            type=ProgressType.PROMPT_START,
            message="Test"
        )
        assert event_no_steps.progress_percentage is None
        
        event_zero_total = ProgressEvent(
            type=ProgressType.FLOW_STEP_START,
            message="Test",
            current_step=1,
            total_steps=0
        )
        assert event_zero_total.progress_percentage is None
    
    def test_progress_event_to_dict(self):
        """Test event serialization to dictionary."""
        event = ProgressEvent(
            type=ProgressType.FLOW_COMPLETE,
            message="Flow completed",
            current_step=3,
            total_steps=3,
            metadata={"outputs": ["result1", "result2"]}
        )
        
        event_dict = event.to_dict()
        
        assert event_dict["type"] == "flow_complete"
        assert event_dict["message"] == "Flow completed"
        assert event_dict["current_step"] == 3
        assert event_dict["total_steps"] == 3
        assert event_dict["progress_percentage"] == 100.0
        assert event_dict["metadata"] == {"outputs": ["result1", "result2"]}
        assert "timestamp" in event_dict


class TestProgressTracker:
    """Test ProgressTracker utility class."""
    
    def test_progress_tracker_basic(self):
        """Test basic progress tracking functionality."""
        tracker = ProgressTracker()
        
        # Initially empty
        assert len(tracker.events) == 0
        assert tracker.current_progress is None
        assert tracker.duration is None
        
        # Add events
        start_event = ProgressEvent(
            type=ProgressType.PROMPT_START,
            message="Starting"
        )
        tracker.track(start_event)
        
        complete_event = ProgressEvent(
            type=ProgressType.PROMPT_COMPLETE,
            message="Complete"
        )
        tracker.track(complete_event)
        
        assert len(tracker.events) == 2
        assert tracker.current_progress == complete_event
        assert tracker.duration is not None
        assert tracker.duration >= 0
    
    def test_progress_tracker_filtering(self):
        """Test filtering events by type."""
        tracker = ProgressTracker()
        
        events = [
            ProgressEvent(ProgressType.PROMPT_START, "Start 1"),
            ProgressEvent(ProgressType.PROMPT_COMPLETE, "Complete 1"),
            ProgressEvent(ProgressType.PROMPT_START, "Start 2"),
            ProgressEvent(ProgressType.FLOW_START, "Flow start"),
        ]
        
        for event in events:
            tracker.track(event)
        
        start_events = tracker.get_events_by_type(ProgressType.PROMPT_START)
        assert len(start_events) == 2
        
        flow_events = tracker.get_events_by_type(ProgressType.FLOW_START)
        assert len(flow_events) == 1
    
    def test_progress_tracker_summary(self):
        """Test summary generation."""
        tracker = ProgressTracker()
        
        # Empty tracker
        summary = tracker.to_summary()
        assert summary["status"] == "no_events"
        
        # Add events
        tracker.track(ProgressEvent(ProgressType.FLOW_START, "Start"))
        tracker.track(ProgressEvent(ProgressType.FLOW_COMPLETE, "Complete"))
        
        summary = tracker.to_summary()
        assert summary["status"] == "complete"
        assert summary["total_events"] == 2
        assert "start_time" in summary
        assert "end_time" in summary
        assert "duration_seconds" in summary
        
        # Test error status
        error_tracker = ProgressTracker()
        error_tracker.track(ProgressEvent(ProgressType.FLOW_START, "Start"))
        error_tracker.track(ProgressEvent(ProgressType.FLOW_ERROR, "Error"))
        
        error_summary = error_tracker.to_summary()
        assert error_summary["status"] == "error"


class TestCLIProgressReporter:
    """Test CLI progress reporting functionality."""
    
    def test_cli_reporter_creation(self):
        """Test CLI reporter creation with different options."""
        # Basic reporter
        reporter = CLIProgressReporter()
        assert not reporter.verbose
        assert not reporter.quiet
        
        # Verbose reporter
        verbose_reporter = CLIProgressReporter(verbose=True)
        assert verbose_reporter.verbose
        
        # Quiet reporter
        quiet_reporter = CLIProgressReporter(quiet=True)
        assert quiet_reporter.quiet
    
    def test_cli_reporter_flow_events(self, capsys):
        """Test flow event reporting."""
        reporter = CLIProgressReporter(verbose=True)
        
        # Flow start
        start_event = ProgressEvent(
            type=ProgressType.FLOW_START,
            message="Starting flow: test_flow",
            total_steps=2,
            metadata={"execution_order": ["step1", "step2"]}
        )
        reporter.report(start_event)
        
        captured = capsys.readouterr()
        assert "🚀" in captured.err
        assert "Starting flow: test_flow" in captured.err
        assert "Total steps: 2" in captured.err
        assert "step1 → step2" in captured.err
        
        # Flow step start
        step_event = ProgressEvent(
            type=ProgressType.FLOW_STEP_START,
            message="Executing step: step1",
            current_step=1,
            total_steps=2,
            step_name="step1",
            metadata={"prompt_name": "test_prompt"}
        )
        reporter.report(step_event)
        
        captured = capsys.readouterr()
        assert "📝" in captured.err
        assert "[1/2]" in captured.err
        assert "(50%)" in captured.err
        assert "Executing step: step1" in captured.err
        assert "Prompt: test_prompt" in captured.err
    
    def test_cli_reporter_quiet_mode(self, capsys):
        """Test that quiet mode suppresses non-error events."""
        reporter = CLIProgressReporter(quiet=True)
        
        # Normal events should be suppressed
        reporter.report(ProgressEvent(ProgressType.FLOW_START, "Start"))
        reporter.report(ProgressEvent(ProgressType.PROMPT_COMPLETE, "Complete"))
        
        captured = capsys.readouterr()
        assert captured.err == ""
        
        # Error events should still show
        reporter.report(ProgressEvent(ProgressType.FLOW_ERROR, "Error occurred"))
        
        captured = capsys.readouterr()
        assert "❌" in captured.err
        assert "Error occurred" in captured.err
    
    def test_cli_reporter_error_events(self, capsys):
        """Test error event reporting."""
        reporter = CLIProgressReporter()
        
        error_event = ProgressEvent(
            type=ProgressType.PROMPT_ERROR,
            message="Error in prompt 'test': API failed",
            metadata={"error_type": "APIError"}
        )
        reporter.report(error_event)
        
        captured = capsys.readouterr()
        assert "❌" in captured.err
        assert "Error in prompt 'test': API failed" in captured.err


class TestStreamingProgressReporter:
    """Test streaming progress reporter with animation."""
    
    def test_streaming_reporter_creation(self):
        """Test streaming reporter creation."""
        reporter = StreamingProgressReporter()
        assert not reporter.verbose
        assert reporter.current_message == ""
        assert len(reporter.spinner_chars) > 0
    
    def test_streaming_reporter_events(self, capsys):
        """Test streaming reporter event handling."""
        reporter = StreamingProgressReporter(verbose=True)
        
        # Start event should trigger spinner
        start_event = ProgressEvent(ProgressType.PROMPT_START, "Processing...")
        reporter.report(start_event)
        
        # Add small delay to avoid the 0.1 second throttling
        time.sleep(0.11)
        
        # Complete event should clear spinner and show completion
        complete_event = ProgressEvent(ProgressType.PROMPT_COMPLETE, "Done")
        reporter.report(complete_event)
        
        captured = capsys.readouterr()
        assert "✅" in captured.out
        assert "Done" in captured.out


class TestCreateCLIReporter:
    """Test CLI reporter factory function."""
    
    def test_create_standard_reporter(self):
        """Test creating standard CLI reporter."""
        reporter = create_cli_reporter(verbose=True, quiet=False)
        assert isinstance(reporter, CLIProgressReporter)
        assert reporter.verbose
        assert not reporter.quiet
    
    def test_create_streaming_reporter(self):
        """Test creating streaming reporter."""
        reporter = create_cli_reporter(verbose=True, streaming=True)
        assert isinstance(reporter, StreamingProgressReporter)
        assert reporter.verbose


class TestCreateSimpleCallback:
    """Test simple callback factory function."""
    
    def test_simple_callback_creation(self, capsys):
        """Test simple callback creation and usage."""
        callback = create_simple_callback(verbose=True)
        
        # Test flow events
        callback(ProgressEvent(ProgressType.FLOW_START, "Starting", total_steps=2))
        callback(ProgressEvent(ProgressType.FLOW_STEP_START, "Step 1", current_step=1, total_steps=2))
        callback(ProgressEvent(ProgressType.FLOW_COMPLETE, "Done"))
        
        captured = capsys.readouterr()
        assert "🚀" in captured.out
        assert "📝" in captured.out  
        assert "🎉" in captured.out


# Integration tests would go here but require actual Orac setup
# These would test the progress callbacks in real Orac and FlowEngine usage
class TestProgressIntegration:
    """Test progress tracking integration with Orac components."""
    
    def test_progress_callback_interface(self):
        """Test that progress callback interface works correctly."""
        events = []
        
        def capture_progress(event: ProgressEvent):
            events.append(event)
        
        # This would be a real test with a mock Orac instance
        # For now, just verify the interface works
        event = ProgressEvent(ProgressType.PROMPT_START, "Test")
        capture_progress(event)
        
        assert len(events) == 1
        assert events[0].type == ProgressType.PROMPT_START
        assert events[0].message == "Test"
    
    def test_progress_event_types_coverage(self):
        """Test that all defined progress types are covered."""
        all_types = {
            ProgressType.PROMPT_START,
            ProgressType.PROMPT_COMPLETE,
            ProgressType.PROMPT_ERROR,
            ProgressType.FLOW_START,
            ProgressType.FLOW_STEP_START,
            ProgressType.FLOW_STEP_COMPLETE,
            ProgressType.FLOW_COMPLETE,
            ProgressType.FLOW_ERROR,
            ProgressType.API_REQUEST_START,
            ProgressType.API_REQUEST_COMPLETE,
            ProgressType.FILE_UPLOAD_START,
            ProgressType.FILE_UPLOAD_COMPLETE
        }
        
        # Verify all enum values are as expected
        actual_types = set(ProgressType)
        assert actual_types == all_types
        
        # Verify string values are lowercase with underscores
        for ptype in ProgressType:
            assert ptype.value.islower()
            assert " " not in ptype.value
            
    def test_metadata_extensibility(self):
        """Test that metadata can be extended for different event types."""
        # Test different metadata structures
        prompt_metadata = {
            "prompt_name": "test",
            "params": {"country": "France"},
            "model_name": "gpt-4"
        }
        
        flow_metadata = {
            "flow_name": "research_flow",
            "step_name": "analyze", 
            "execution_order": ["gather", "analyze", "report"],
            "completed_steps": ["gather"]
        }
        
        api_metadata = {
            "files_count": 3,
            "message_history_length": 5,
            "response_length": 1024,
            "model_used": "gpt-4"
        }
        
        # All should work without issues
        events = [
            ProgressEvent(ProgressType.PROMPT_START, "Test", metadata=prompt_metadata),
            ProgressEvent(ProgressType.FLOW_STEP_START, "Test", metadata=flow_metadata),
            ProgressEvent(ProgressType.API_REQUEST_COMPLETE, "Test", metadata=api_metadata)
        ]
        
        assert all(event.metadata for event in events)
        assert events[0].metadata["prompt_name"] == "test"
        assert events[1].metadata["flow_name"] == "research_flow"
        assert events[2].metadata["files_count"] == 3


if __name__ == "__main__":
    pytest.main([__file__])