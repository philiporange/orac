"""
Focused unit tests for progress tracking functionality.

These tests focus on isolated unit testing of individual components,
using mocks and stubs to avoid external dependencies.
"""
import pytest
from unittest.mock import Mock, patch, call
from datetime import datetime, timedelta
import json
import io
import sys

from orac.progress import (
    ProgressEvent, ProgressType, ProgressCallback, ProgressTracker,
    create_simple_callback
)
from orac.cli_progress import CLIProgressReporter, StreamingProgressReporter, create_cli_reporter


class TestProgressEventUnit:
    """Unit tests for ProgressEvent class."""
    
    @pytest.mark.unit
    def test_progress_event_initialization(self):
        """Test ProgressEvent initialization with all fields."""
        timestamp = datetime.now()
        event = ProgressEvent(
            type=ProgressType.PROMPT_START,
            message="Test message",
            current_step=2,
            total_steps=5,
            step_name="test_step",
            metadata={"key": "value"},
            timestamp=timestamp
        )
        
        assert event.type == ProgressType.PROMPT_START
        assert event.message == "Test message"
        assert event.current_step == 2
        assert event.total_steps == 5
        assert event.step_name == "test_step"
        assert event.metadata == {"key": "value"}
        assert event.timestamp == timestamp
    
    @pytest.mark.unit
    def test_progress_event_auto_timestamp(self):
        """Test that timestamp is auto-populated if not provided."""
        before = datetime.now()
        event = ProgressEvent(ProgressType.PROMPT_START, "Test")
        after = datetime.now()
        
        assert event.timestamp is not None
        assert before <= event.timestamp <= after
    
    @pytest.mark.unit
    def test_progress_percentage_calculation(self):
        """Test progress percentage calculation logic."""
        # Normal case
        event = ProgressEvent(ProgressType.FLOW_STEP_START, "Test", current_step=3, total_steps=4)
        assert event.progress_percentage == 75.0
        
        # Edge case: first step
        event_first = ProgressEvent(ProgressType.FLOW_STEP_START, "Test", current_step=1, total_steps=10)
        assert event_first.progress_percentage == 10.0
        
        # Edge case: last step
        event_last = ProgressEvent(ProgressType.FLOW_STEP_START, "Test", current_step=10, total_steps=10)
        assert event_last.progress_percentage == 100.0
        
        # Edge case: no step info
        event_no_steps = ProgressEvent(ProgressType.PROMPT_START, "Test")
        assert event_no_steps.progress_percentage is None
        
        # Edge case: zero total steps
        event_zero = ProgressEvent(ProgressType.FLOW_STEP_START, "Test", current_step=1, total_steps=0)
        assert event_zero.progress_percentage is None
    
    @pytest.mark.unit
    def test_progress_event_to_dict(self):
        """Test event serialization to dictionary."""
        timestamp = datetime(2024, 1, 15, 14, 30, 45)
        event = ProgressEvent(
            type=ProgressType.FLOW_COMPLETE,
            message="Flow completed",
            current_step=3,
            total_steps=3,
            step_name="final_step",
            metadata={"outputs": ["result1", "result2"]},
            timestamp=timestamp
        )
        
        result = event.to_dict()
        
        expected = {
            "type": "flow_complete",
            "message": "Flow completed",
            "current_step": 3,
            "total_steps": 3,
            "step_name": "final_step",
            "metadata": {"outputs": ["result1", "result2"]},
            "timestamp": "2024-01-15T14:30:45",
            "progress_percentage": 100.0
        }
        
        assert result == expected
    
    @pytest.mark.unit
    def test_progress_event_minimal(self):
        """Test ProgressEvent with minimal required fields."""
        event = ProgressEvent(ProgressType.PROMPT_ERROR, "Error occurred")
        
        assert event.type == ProgressType.PROMPT_ERROR
        assert event.message == "Error occurred"
        assert event.current_step is None
        assert event.total_steps is None
        assert event.step_name is None
        assert event.metadata is None
        assert event.timestamp is not None
        assert event.progress_percentage is None


class TestProgressTrackerUnit:
    """Unit tests for ProgressTracker utility."""
    
    @pytest.mark.unit
    def test_progress_tracker_initialization(self):
        """Test ProgressTracker initialization."""
        tracker = ProgressTracker()
        
        assert tracker.events == []
        assert tracker.start_time is None
        assert tracker.end_time is None
        assert tracker.duration is None
        assert tracker.current_progress is None
    
    @pytest.mark.unit
    def test_progress_tracker_single_event(self):
        """Test tracking a single event."""
        tracker = ProgressTracker()
        event = ProgressEvent(ProgressType.PROMPT_START, "Starting")
        
        tracker.track(event)
        
        assert len(tracker.events) == 1
        assert tracker.events[0] == event
        assert tracker.start_time == event.timestamp
        assert tracker.end_time is None
        assert tracker.current_progress == event
    
    @pytest.mark.unit
    def test_progress_tracker_completion_flow(self):
        """Test tracking from start to completion."""
        tracker = ProgressTracker()
        
        start_event = ProgressEvent(ProgressType.PROMPT_START, "Starting")
        tracker.track(start_event)
        
        complete_event = ProgressEvent(ProgressType.PROMPT_COMPLETE, "Done")
        tracker.track(complete_event)
        
        assert len(tracker.events) == 2
        assert tracker.start_time == start_event.timestamp
        assert tracker.end_time == complete_event.timestamp
        assert tracker.current_progress == complete_event
        assert tracker.duration is not None
        assert tracker.duration >= 0
    
    @pytest.mark.unit
    def test_progress_tracker_error_handling(self):
        """Test tracking error events."""
        tracker = ProgressTracker()
        
        start_event = ProgressEvent(ProgressType.FLOW_START, "Starting")
        error_event = ProgressEvent(ProgressType.FLOW_ERROR, "Failed")
        
        tracker.track(start_event)
        tracker.track(error_event)
        
        assert tracker.end_time == error_event.timestamp
        
        summary = tracker.to_summary()
        assert summary["status"] == "error"
    
    @pytest.mark.unit
    def test_progress_tracker_filtering(self):
        """Test filtering events by type."""
        tracker = ProgressTracker()
        
        events = [
            ProgressEvent(ProgressType.PROMPT_START, "Start 1"),
            ProgressEvent(ProgressType.API_REQUEST_START, "API Start"),
            ProgressEvent(ProgressType.PROMPT_START, "Start 2"),
            ProgressEvent(ProgressType.PROMPT_COMPLETE, "Complete 1"),
        ]
        
        for event in events:
            tracker.track(event)
        
        prompt_starts = tracker.get_events_by_type(ProgressType.PROMPT_START)
        assert len(prompt_starts) == 2
        assert all(e.type == ProgressType.PROMPT_START for e in prompt_starts)
        
        api_events = tracker.get_events_by_type(ProgressType.API_REQUEST_START)
        assert len(api_events) == 1
        
        nonexistent = tracker.get_events_by_type(ProgressType.FILE_UPLOAD_START)
        assert len(nonexistent) == 0
    
    @pytest.mark.unit
    def test_progress_tracker_summary_states(self):
        """Test summary generation for different states."""
        # Empty tracker
        empty_tracker = ProgressTracker()
        summary = empty_tracker.to_summary()
        assert summary["status"] == "no_events"
        assert summary["events"] == []
        
        # In-progress tracker
        in_progress_tracker = ProgressTracker()
        in_progress_tracker.track(ProgressEvent(ProgressType.FLOW_START, "Starting"))
        in_progress_tracker.track(ProgressEvent(ProgressType.FLOW_STEP_START, "Step 1"))
        
        summary = in_progress_tracker.to_summary()
        assert summary["status"] == "in_progress"
        assert summary["total_events"] == 2
        
        # Completed tracker
        completed_tracker = ProgressTracker()
        completed_tracker.track(ProgressEvent(ProgressType.FLOW_START, "Starting"))
        completed_tracker.track(ProgressEvent(ProgressType.FLOW_COMPLETE, "Done"))
        
        summary = completed_tracker.to_summary()
        assert summary["status"] == "complete"
        
        # Error tracker
        error_tracker = ProgressTracker()
        error_tracker.track(ProgressEvent(ProgressType.FLOW_START, "Starting"))
        error_tracker.track(ProgressEvent(ProgressType.FLOW_ERROR, "Failed"))
        
        summary = error_tracker.to_summary()
        assert summary["status"] == "error"


class TestCLIProgressReporterUnit:
    """Unit tests for CLIProgressReporter."""
    
    @pytest.mark.unit
    def test_cli_reporter_initialization(self):
        """Test CLIProgressReporter initialization."""
        # Default
        reporter = CLIProgressReporter()
        assert not reporter.verbose
        assert not reporter.quiet
        assert reporter.start_time is not None
        
        # With options
        verbose_reporter = CLIProgressReporter(verbose=True, quiet=False)
        assert verbose_reporter.verbose
        assert not verbose_reporter.quiet
        
        quiet_reporter = CLIProgressReporter(verbose=False, quiet=True)
        assert not quiet_reporter.verbose
        assert quiet_reporter.quiet
    
    @pytest.mark.unit
    def test_cli_reporter_quiet_mode_suppression(self, capsys):
        """Test that quiet mode suppresses non-error events."""
        reporter = CLIProgressReporter(quiet=True)
        
        # These should be suppressed
        non_error_events = [
            ProgressEvent(ProgressType.FLOW_START, "Starting"),
            ProgressEvent(ProgressType.PROMPT_START, "Prompt starting"),
            ProgressEvent(ProgressType.FLOW_STEP_COMPLETE, "Step done"),
            ProgressEvent(ProgressType.FLOW_COMPLETE, "All done"),
        ]
        
        for event in non_error_events:
            reporter.report(event)
        
        captured = capsys.readouterr()
        assert captured.err == ""
        assert captured.out == ""
        
        # Error events should still show
        error_events = [
            ProgressEvent(ProgressType.PROMPT_ERROR, "Prompt failed"),
            ProgressEvent(ProgressType.FLOW_ERROR, "Flow failed"),
        ]
        
        for event in error_events:
            reporter.report(event)
        
        captured = capsys.readouterr()
        assert "❌" in captured.err
        assert "Prompt failed" in captured.err
        assert "Flow failed" in captured.err
    
    @pytest.mark.unit
    def test_cli_reporter_verbose_mode(self, capsys):
        """Test verbose mode shows additional details."""
        reporter = CLIProgressReporter(verbose=True)
        
        # Flow step with metadata
        event = ProgressEvent(
            type=ProgressType.FLOW_STEP_START,
            message="Executing step: analyze",
            current_step=2,
            total_steps=3,
            step_name="analyze",
            metadata={"prompt_name": "data_analysis"}
        )
        
        reporter.report(event)
        
        captured = capsys.readouterr()
        assert "📝" in captured.err
        assert "[2/3]" in captured.err
        assert "(67%)" in captured.err
        assert "Executing step: analyze" in captured.err
        assert "Prompt: data_analysis" in captured.err
    
    @pytest.mark.unit
    def test_cli_reporter_flow_flow(self, capsys):
        """Test complete flow reporting flow."""
        reporter = CLIProgressReporter(verbose=True)
        
        # Start
        start_event = ProgressEvent(
            type=ProgressType.FLOW_START,
            message="Starting flow: test_flow",
            total_steps=2,
            metadata={"execution_order": ["step1", "step2"]}
        )
        reporter.report(start_event)
        
        # Step 1 start
        step1_start = ProgressEvent(
            type=ProgressType.FLOW_STEP_START,
            message="Executing step: step1",
            current_step=1,
            total_steps=2,
            step_name="step1"
        )
        reporter.report(step1_start)
        reporter.last_step_time = datetime.now() - timedelta(seconds=5)  # Simulate 5s ago
        
        # Step 1 complete
        step1_complete = ProgressEvent(
            type=ProgressType.FLOW_STEP_COMPLETE,
            message="Completed step: step1",
            step_name="step1",
            metadata={"result_keys": ["output1", "output2"]}
        )
        reporter.report(step1_complete)
        
        # Flow complete
        flow_complete = ProgressEvent(
            type=ProgressType.FLOW_COMPLETE,
            message="Completed flow: test_flow",
            metadata={"outputs": ["final_result"]}
        )
        reporter.report(flow_complete)
        
        captured = capsys.readouterr()
        
        # Check all expected elements are present
        assert "🚀" in captured.err
        assert "Starting flow: test_flow" in captured.err
        assert "step1 → step2" in captured.err
        assert "📝" in captured.err
        assert "[1/2]" in captured.err
        assert "✅" in captured.err
        assert "Step completed: step1" in captured.err
        assert "🎉" in captured.err
        assert "Completed flow: test_flow" in captured.err
    
    @pytest.mark.unit
    def test_cli_reporter_error_events(self, capsys):
        """Test error event reporting."""
        reporter = CLIProgressReporter(verbose=True)
        
        error_event = ProgressEvent(
            type=ProgressType.PROMPT_ERROR,
            message="Error in prompt 'test': Connection failed",
            metadata={"error_type": "ConnectionError", "prompt_name": "test"}
        )
        
        reporter.report(error_event)
        
        captured = capsys.readouterr()
        assert "❌" in captured.err
        assert "Error in prompt 'test': Connection failed" in captured.err
        assert "Error type: ConnectionError" in captured.err


class TestStreamingProgressReporterUnit:
    """Unit tests for StreamingProgressReporter."""
    
    @pytest.mark.unit
    def test_streaming_reporter_initialization(self):
        """Test StreamingProgressReporter initialization."""
        reporter = StreamingProgressReporter()
        
        assert not reporter.verbose
        assert reporter.current_message == ""
        assert len(reporter.spinner_chars) > 0
        assert reporter.spinner_index == 0
        assert reporter.last_update is not None
    
    @pytest.mark.unit
    def test_streaming_reporter_verbose_mode(self):
        """Test verbose mode configuration."""
        reporter = StreamingProgressReporter(verbose=True)
        
        assert reporter.verbose
    
    @pytest.mark.unit
    @patch('sys.stderr')
    def test_streaming_reporter_spinner_display(self, mock_stderr):
        """Test spinner display functionality."""
        reporter = StreamingProgressReporter()
        
        # Test spinner display
        reporter.current_message = "Processing..."
        reporter._show_spinner()
        
        # Verify stderr.write was called
        mock_stderr.write.assert_called()
        mock_stderr.flush.assert_called()
        
        # Verify spinner character is included
        call_args = mock_stderr.write.call_args[0][0]
        assert "Processing..." in call_args
        assert any(char in call_args for char in reporter.spinner_chars)
    
    @pytest.mark.unit
    @patch('sys.stderr')
    def test_streaming_reporter_spinner_clearing(self, mock_stderr):
        """Test spinner clearing functionality."""
        reporter = StreamingProgressReporter()
        
        reporter._clear_spinner()
        
        # Verify clearing sequence
        mock_stderr.write.assert_called()
        mock_stderr.flush.assert_called()
        
        # Should write spaces to clear the line
        call_args = mock_stderr.write.call_args[0][0]
        assert ' ' in call_args
    
    @pytest.mark.unit
    def test_streaming_reporter_event_handling(self, capsys):
        """Test streaming reporter event handling."""
        reporter = StreamingProgressReporter(verbose=True)
        
        # Mock time to ensure updates occur (need to account for throttling)
        with patch('time.time') as mock_time:
            # Set initial time for reporter initialization
            mock_time.return_value = 0
            reporter.last_update = 0
            
            # Now set up times that will pass the throttling check
            mock_time.side_effect = [0.2, 0.4]  # Each call is >0.1s apart
            
            # Start event
            start_event = ProgressEvent(ProgressType.PROMPT_START, "Processing data...")
            reporter.report(start_event)
            
            # Complete event  
            complete_event = ProgressEvent(ProgressType.PROMPT_COMPLETE, "Data processed")
            reporter.report(complete_event)
            
        captured = capsys.readouterr()
        # Verbose completion should print to stdout
        assert "✅" in captured.out
        assert "Data processed" in captured.out


class TestCreateSimpleCallbackUnit:
    """Unit tests for create_simple_callback factory function."""
    
    @pytest.mark.unit
    def test_create_simple_callback_verbose(self, capsys):
        """Test creating verbose simple callback."""
        callback = create_simple_callback(verbose=True)
        assert callable(callback)
        
        # Test with various event types
        events = [
            ProgressEvent(ProgressType.FLOW_START, "Starting flow", total_steps=2),
            ProgressEvent(ProgressType.FLOW_STEP_START, "Step 1", current_step=1, total_steps=2),
            ProgressEvent(ProgressType.PROMPT_START, "Prompt starting"),
            ProgressEvent(ProgressType.PROMPT_COMPLETE, "Prompt done"),
            ProgressEvent(ProgressType.FLOW_STEP_COMPLETE, "Step done", step_name="step1"),
            ProgressEvent(ProgressType.FLOW_COMPLETE, "All done"),
        ]
        
        for event in events:
            callback(event)
        
        captured = capsys.readouterr()
        
        # Verify expected outputs
        assert "🚀" in captured.out  # Flow start
        assert "📝" in captured.out  # Step start
        assert "⏳" in captured.out  # Prompt start (verbose)
        assert "✅" in captured.out  # Completions
        assert "🎉" in captured.out  # Flow complete
    
    @pytest.mark.unit
    def test_create_simple_callback_non_verbose(self, capsys):
        """Test creating non-verbose simple callback."""
        callback = create_simple_callback(verbose=False)
        
        # Prompt events should be suppressed in non-verbose mode
        callback(ProgressEvent(ProgressType.PROMPT_START, "Prompt starting"))
        callback(ProgressEvent(ProgressType.PROMPT_COMPLETE, "Prompt done"))
        
        captured = capsys.readouterr()
        assert "⏳" not in captured.out  # Should not show prompt start
        assert captured.out == ""  # Should be empty for non-verbose prompt events
        
        # But flow events should still show
        callback(ProgressEvent(ProgressType.FLOW_START, "Flow starting"))
        
        captured = capsys.readouterr()
        assert "🚀" in captured.out


class TestCreateCLIReporterUnit:
    """Unit tests for create_cli_reporter factory function."""
    
    @pytest.mark.unit
    def test_create_standard_cli_reporter(self):
        """Test creating standard CLI reporter."""
        reporter = create_cli_reporter(verbose=True, quiet=False, streaming=False)
        
        assert isinstance(reporter, CLIProgressReporter)
        assert reporter.verbose is True
        assert reporter.quiet is False
    
    @pytest.mark.unit
    def test_create_streaming_cli_reporter(self):
        """Test creating streaming CLI reporter."""
        reporter = create_cli_reporter(verbose=True, streaming=True)
        
        assert isinstance(reporter, StreamingProgressReporter)
        assert reporter.verbose is True
    
    @pytest.mark.unit
    def test_create_quiet_cli_reporter(self):
        """Test creating quiet CLI reporter."""
        reporter = create_cli_reporter(verbose=False, quiet=True, streaming=False)
        
        assert isinstance(reporter, CLIProgressReporter)
        assert reporter.verbose is False
        assert reporter.quiet is True
    
    @pytest.mark.unit
    def test_create_default_cli_reporter(self):
        """Test creating CLI reporter with defaults."""
        reporter = create_cli_reporter()
        
        assert isinstance(reporter, CLIProgressReporter)
        assert reporter.verbose is False
        assert reporter.quiet is False


class TestProgressTypeEnumUnit:
    """Unit tests for ProgressType enum."""
    
    @pytest.mark.unit
    def test_progress_type_values(self):
        """Test that all ProgressType values are as expected."""
        expected_types = {
            ProgressType.PROMPT_START: "prompt_start",
            ProgressType.PROMPT_COMPLETE: "prompt_complete",
            ProgressType.PROMPT_ERROR: "prompt_error",
            ProgressType.FLOW_START: "flow_start",
            ProgressType.FLOW_STEP_START: "flow_step_start",
            ProgressType.FLOW_STEP_COMPLETE: "flow_step_complete",
            ProgressType.FLOW_COMPLETE: "flow_complete",
            ProgressType.FLOW_ERROR: "flow_error",
            ProgressType.API_REQUEST_START: "api_request_start",
            ProgressType.API_REQUEST_COMPLETE: "api_request_complete",
            ProgressType.FILE_UPLOAD_START: "file_upload_start",
            ProgressType.FILE_UPLOAD_COMPLETE: "file_upload_complete",
        }
        
        for enum_val, string_val in expected_types.items():
            assert enum_val.value == string_val
    
    @pytest.mark.unit
    def test_progress_type_string_format(self):
        """Test that all ProgressType values follow naming conventions."""
        for progress_type in ProgressType:
            # Should be lowercase
            assert progress_type.value.islower()
            # Should use underscores, not spaces
            assert ' ' not in progress_type.value
            # Should not be empty
            assert len(progress_type.value) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])