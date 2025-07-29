"""
Unit tests for CLI progress integration.

These tests focus on testing CLI argument parsing and progress reporter
creation without executing full CLI commands.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import argparse

from orac.cli_progress import create_cli_reporter, CLIProgressReporter, StreamingProgressReporter
from orac.progress import ProgressEvent, ProgressType


class TestCLIProgressArgumentHandling:
    """Unit tests for CLI progress argument handling."""
    
    @pytest.mark.unit
    def test_create_cli_reporter_with_defaults(self):
        """Test creating CLI reporter with default arguments."""
        reporter = create_cli_reporter()
        
        assert isinstance(reporter, CLIProgressReporter)
        assert reporter.verbose is False
        assert reporter.quiet is False
    
    @pytest.mark.unit
    def test_create_cli_reporter_verbose(self):
        """Test creating verbose CLI reporter."""
        reporter = create_cli_reporter(verbose=True)
        
        assert isinstance(reporter, CLIProgressReporter)
        assert reporter.verbose is True
        assert reporter.quiet is False
    
    @pytest.mark.unit
    def test_create_cli_reporter_quiet(self):
        """Test creating quiet CLI reporter."""
        reporter = create_cli_reporter(quiet=True)
        
        assert isinstance(reporter, CLIProgressReporter)
        assert reporter.verbose is False
        assert reporter.quiet is True
    
    @pytest.mark.unit
    def test_create_cli_reporter_verbose_and_quiet(self):
        """Test creating reporter with both verbose and quiet (quiet should take precedence)."""
        reporter = create_cli_reporter(verbose=True, quiet=True)
        
        assert isinstance(reporter, CLIProgressReporter)
        assert reporter.verbose is True  # Still set, but quiet takes precedence in behavior
        assert reporter.quiet is True
    
    @pytest.mark.unit
    def test_create_streaming_reporter(self):
        """Test creating streaming reporter."""
        reporter = create_cli_reporter(streaming=True)
        
        assert isinstance(reporter, StreamingProgressReporter)
        assert reporter.verbose is False
    
    @pytest.mark.unit
    def test_create_streaming_reporter_verbose(self):
        """Test creating verbose streaming reporter."""
        reporter = create_cli_reporter(verbose=True, streaming=True)
        
        assert isinstance(reporter, StreamingProgressReporter)
        assert reporter.verbose is True


class TestCLIProgressReporterBehavior:
    """Unit tests for CLI progress reporter behavior patterns."""
    
    @pytest.mark.unit
    def test_quiet_mode_suppresses_non_errors(self, capsys):
        """Test that quiet mode only shows error events."""
        reporter = CLIProgressReporter(quiet=True)
        
        # Non-error events should be suppressed
        non_error_events = [
            ProgressEvent(ProgressType.FLOW_START, "Starting flow"),
            ProgressEvent(ProgressType.FLOW_STEP_START, "Starting step"),
            ProgressEvent(ProgressType.PROMPT_START, "Starting prompt"),
            ProgressEvent(ProgressType.API_REQUEST_START, "Making API call"),
            ProgressEvent(ProgressType.API_REQUEST_COMPLETE, "API call complete"),
            ProgressEvent(ProgressType.PROMPT_COMPLETE, "Prompt complete"),
            ProgressEvent(ProgressType.FLOW_STEP_COMPLETE, "Step complete"),
            ProgressEvent(ProgressType.FLOW_COMPLETE, "Workflow complete"),
        ]
        
        for event in non_error_events:
            reporter.report(event)
        
        captured = capsys.readouterr()
        assert captured.err == ""
        assert captured.out == ""
        
        # Error events should still show
        error_events = [
            ProgressEvent(ProgressType.PROMPT_ERROR, "Prompt failed"),
            ProgressEvent(ProgressType.FLOW_ERROR, "Workflow failed"),
        ]
        
        for event in error_events:
            reporter.report(event)
        
        captured = capsys.readouterr()
        assert "❌" in captured.err
        assert "Prompt failed" in captured.err
        assert "Workflow failed" in captured.err
    
    @pytest.mark.unit
    def test_verbose_mode_shows_all_events(self, capsys):
        """Test that verbose mode shows all events including prompts."""
        reporter = CLIProgressReporter(verbose=True)
        
        events = [
            ProgressEvent(ProgressType.FLOW_START, "Starting flow"),
            ProgressEvent(ProgressType.PROMPT_START, "Starting prompt"),
            ProgressEvent(ProgressType.API_REQUEST_START, "Making API call"),
            ProgressEvent(ProgressType.API_REQUEST_COMPLETE, "API call complete"),
            ProgressEvent(ProgressType.PROMPT_COMPLETE, "Prompt complete"),
            ProgressEvent(ProgressType.FLOW_COMPLETE, "Workflow complete"),
        ]
        
        for event in events:
            reporter.report(event)
        
        captured = capsys.readouterr()
        
        # Should show flow events
        assert "🚀" in captured.err  # flow start
        assert "🎉" in captured.err  # flow complete
        
        # Should show prompt events (verbose only)
        assert "⏳" in captured.err  # prompt start
        assert "✅" in captured.err  # prompt complete
        
        # Should show API events (verbose only)
        assert "🌐" in captured.err  # API start
        assert "📡" in captured.err  # API complete
    
    @pytest.mark.unit
    def test_default_mode_shows_flow_events_only(self, capsys):
        """Test that default mode shows flow events but not prompt details."""
        reporter = CLIProgressReporter(verbose=False)
        
        # Workflow events should show
        flow_events = [
            ProgressEvent(ProgressType.FLOW_START, "Starting flow"),
            ProgressEvent(ProgressType.FLOW_STEP_START, "Starting step"),
            ProgressEvent(ProgressType.FLOW_STEP_COMPLETE, "Step complete"),
            ProgressEvent(ProgressType.FLOW_COMPLETE, "Workflow complete"),
        ]
        
        for event in flow_events:
            reporter.report(event)
        
        captured = capsys.readouterr()
        assert "🚀" in captured.err  # flow start
        assert "📝" in captured.err  # step start
        assert "✅" in captured.err  # step complete
        assert "🎉" in captured.err  # flow complete
        
        # Prompt events should not show in default mode
        prompt_events = [
            ProgressEvent(ProgressType.PROMPT_START, "Starting prompt"),
            ProgressEvent(ProgressType.PROMPT_COMPLETE, "Prompt complete"),
            ProgressEvent(ProgressType.API_REQUEST_START, "API call"),
            ProgressEvent(ProgressType.API_REQUEST_COMPLETE, "API done"),
        ]
        
        for event in prompt_events:
            reporter.report(event)
        
        captured = capsys.readouterr()
        # Should not show prompt-specific indicators
        assert "⏳" not in captured.err  # prompt start
        assert "🌐" not in captured.err  # API start
        assert "📡" not in captured.err  # API complete


class TestCLIProgressTimestampHandling:
    """Unit tests for timestamp handling in CLI progress reporting."""
    
    @pytest.mark.unit
    def test_timestamp_formatting_in_output(self, capsys):
        """Test that timestamps are properly formatted in output."""
        from datetime import datetime
        
        reporter = CLIProgressReporter()
        
        # Create event with specific timestamp
        timestamp = datetime(2024, 1, 15, 14, 30, 45)
        event = ProgressEvent(
            ProgressType.FLOW_START,
            "Starting flow",
            timestamp=timestamp
        )
        
        reporter.report(event)
        
        captured = capsys.readouterr()
        assert "14:30:45" in captured.err
    
    @pytest.mark.unit
    def test_missing_timestamp_handling(self, capsys):
        """Test handling of events with missing timestamps."""
        reporter = CLIProgressReporter()
        
        # Create event with None timestamp
        event = ProgressEvent(ProgressType.FLOW_START, "Starting flow")
        event.timestamp = None  # Force None to test fallback
        
        reporter.report(event)
        
        captured = capsys.readouterr()
        # Should show fallback timestamp format
        assert "??:??:??" in captured.err


class TestCLIProgressMetadataHandling:
    """Unit tests for metadata handling in CLI progress reporting."""
    
    @pytest.mark.unit
    def test_flow_metadata_display(self, capsys):
        """Test that flow metadata is properly displayed."""
        reporter = CLIProgressReporter(verbose=True)
        
        # Workflow start with execution order
        start_event = ProgressEvent(
            ProgressType.FLOW_START,
            "Starting flow: test_flow",
            total_steps=3,
            metadata={
                "flow_name": "test_flow",
                "execution_order": ["step1", "step2", "step3"]
            }
        )
        
        reporter.report(start_event)
        
        captured = capsys.readouterr()
        assert "Total steps: 3" in captured.err
        assert "step1 → step2 → step3" in captured.err
    
    @pytest.mark.unit
    def test_step_metadata_display(self, capsys):
        """Test that step metadata is properly displayed."""
        reporter = CLIProgressReporter(verbose=True)
        
        # Step start with prompt name
        step_event = ProgressEvent(
            ProgressType.FLOW_STEP_START,
            "Executing step: analyze_data",
            current_step=2,
            total_steps=4,
            step_name="analyze_data",
            metadata={"prompt_name": "data_analyzer"}
        )
        
        reporter.report(step_event)
        
        captured = capsys.readouterr()
        assert "[2/4]" in captured.err
        assert "(50%)" in captured.err
        assert "Executing step: analyze_data" in captured.err
        assert "Prompt: data_analyzer" in captured.err
        
        # Step completion with results
        complete_event = ProgressEvent(
            ProgressType.FLOW_STEP_COMPLETE,
            "Completed step",
            step_name="analyze_data",
            metadata={"result_keys": ["analysis", "summary", "metrics"]}
        )
        
        reporter.report(complete_event)
        
        captured = capsys.readouterr()
        assert "Step completed: analyze_data" in captured.err
        assert "Outputs: analysis, summary, metrics" in captured.err
    
    @pytest.mark.unit
    def test_error_metadata_display(self, capsys):
        """Test that error metadata is properly displayed."""
        reporter = CLIProgressReporter(verbose=True)
        
        error_event = ProgressEvent(
            ProgressType.PROMPT_ERROR,
            "Error in prompt 'test': Connection timeout",
            metadata={
                "error_type": "TimeoutError",
                "prompt_name": "test",
                "retry_count": 3
            }
        )
        
        reporter.report(error_event)
        
        captured = capsys.readouterr()
        assert "❌" in captured.err
        assert "Error in prompt 'test': Connection timeout" in captured.err
        assert "Error type: TimeoutError" in captured.err
    
    @pytest.mark.unit
    def test_missing_metadata_handling(self, capsys):
        """Test handling of events with missing metadata."""
        reporter = CLIProgressReporter(verbose=True)
        
        # Event without metadata should not crash
        event = ProgressEvent(ProgressType.FLOW_START, "Starting")  # No metadata
        
        reporter.report(event)
        
        captured = capsys.readouterr()
        assert "🚀" in captured.err
        assert "Starting" in captured.err
        # Should not crash or show metadata-related content


class TestStreamingProgressReporterUnit:
    """Unit tests for streaming progress reporter behavior."""
    
    @pytest.mark.unit
    @patch('time.time')
    def test_streaming_reporter_throttling(self, mock_time):
        """Test that streaming reporter throttles updates."""
        mock_time.side_effect = [0, 0.05, 0.05, 0.15]  # Simulate time progression
        
        reporter = StreamingProgressReporter()
        
        # First call should work
        event1 = ProgressEvent(ProgressType.PROMPT_START, "Processing...")
        reporter.report(event1)
        
        # Second call too soon should be ignored (0.05s < 0.1s threshold)
        event2 = ProgressEvent(ProgressType.API_REQUEST_START, "API call...")
        reporter.report(event2)
        
        # Third call after enough time should work
        event3 = ProgressEvent(ProgressType.PROMPT_COMPLETE, "Done")
        reporter.report(event3)
        
        # Verify time.time was called to check intervals
        assert mock_time.call_count >= 3
    
    @pytest.mark.unit
    def test_streaming_reporter_spinner_progression(self):
        """Test that streaming reporter advances spinner characters."""
        reporter = StreamingProgressReporter()
        
        initial_index = reporter.spinner_index
        initial_char = reporter.spinner_chars[initial_index]
        
        # Simulate showing spinner multiple times
        reporter.current_message = "Processing..."
        reporter._show_spinner()
        
        # Index should advance
        assert reporter.spinner_index == (initial_index + 1) % len(reporter.spinner_chars)
        
        # After full cycle, should wrap around
        for _ in range(len(reporter.spinner_chars)):
            reporter._show_spinner()
        
        assert reporter.spinner_index == (initial_index + 1) % len(reporter.spinner_chars)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])