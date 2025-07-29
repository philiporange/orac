"""
CLI progress reporting for Orac operations.

This module provides user-friendly progress display for command-line usage,
with different verbosity levels and visual feedback for long-running operations.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from typing import Optional, Dict, Any

from .progress import ProgressEvent, ProgressType


class CLIProgressReporter:
    """
    Command-line progress reporter that provides visual feedback for operations.
    
    Features:
    - Timestamps for all events
    - Step counting for workflows
    - Emojis for visual clarity
    - Configurable verbosity levels
    - Error highlighting
    """
    
    def __init__(self, verbose: bool = False, quiet: bool = False):
        """
        Initialize the CLI progress reporter.
        
        Args:
            verbose: Show detailed progress including individual prompts
            quiet: Suppress all progress output except errors
        """
        self.verbose = verbose
        self.quiet = quiet
        self.start_time = datetime.now()
        self.last_step_time: Optional[datetime] = None
        
    def report(self, event: ProgressEvent) -> None:
        """Handle a progress event and display appropriate output."""
        if self.quiet and event.type not in self._error_types():
            return
            
        timestamp = event.timestamp.strftime("%H:%M:%S") if event.timestamp else "??:??:??"
        
        # Handle different event types
        if event.type == ProgressType.WORKFLOW_START:
            self._report_workflow_start(event, timestamp)
        elif event.type == ProgressType.WORKFLOW_STEP_START:
            self._report_workflow_step_start(event, timestamp)
        elif event.type == ProgressType.WORKFLOW_STEP_COMPLETE:
            self._report_workflow_step_complete(event, timestamp)
        elif event.type == ProgressType.WORKFLOW_COMPLETE:
            self._report_workflow_complete(event, timestamp)
        elif event.type == ProgressType.PROMPT_START:
            self._report_prompt_start(event, timestamp)
        elif event.type == ProgressType.PROMPT_COMPLETE:
            self._report_prompt_complete(event, timestamp)
        elif event.type == ProgressType.API_REQUEST_START:
            self._report_api_request_start(event, timestamp)
        elif event.type == ProgressType.API_REQUEST_COMPLETE:
            self._report_api_request_complete(event, timestamp)
        elif event.type in self._error_types():
            self._report_error(event, timestamp)
            
    def _error_types(self) -> set[ProgressType]:
        """Return set of error event types."""
        return {ProgressType.PROMPT_ERROR, ProgressType.WORKFLOW_ERROR}
    
    def _report_workflow_start(self, event: ProgressEvent, timestamp: str) -> None:
        """Report workflow start."""
        print(f"\n🚀 {timestamp} - {event.message}", file=sys.stderr)
        if event.total_steps:
            print(f"   Total steps: {event.total_steps}", file=sys.stderr)
        if self.verbose and event.metadata:
            execution_order = event.metadata.get("execution_order", [])
            if execution_order:
                print(f"   Execution order: {' → '.join(execution_order)}", file=sys.stderr)
    
    def _report_workflow_step_start(self, event: ProgressEvent, timestamp: str) -> None:
        """Report workflow step start."""
        if event.current_step and event.total_steps:
            progress = f"[{event.current_step}/{event.total_steps}]"
            percent = f"({event.progress_percentage:.0f}%)" if event.progress_percentage else ""
            print(f"\n📝 {timestamp} - {progress} {percent} {event.message}", file=sys.stderr)
        else:
            print(f"\n📝 {timestamp} - {event.message}", file=sys.stderr)
        
        # Show prompt name if available
        if self.verbose and event.metadata:
            prompt_name = event.metadata.get("prompt_name")
            if prompt_name:
                print(f"   Prompt: {prompt_name}", file=sys.stderr)
        
        self.last_step_time = event.timestamp
    
    def _report_workflow_step_complete(self, event: ProgressEvent, timestamp: str) -> None:
        """Report workflow step completion."""
        duration_str = ""
        if self.last_step_time and event.timestamp:
            duration = (event.timestamp - self.last_step_time).total_seconds()
            duration_str = f" ({duration:.1f}s)"
        
        step_name = event.step_name or "unknown"
        print(f"✅ {timestamp} - Step completed: {step_name}{duration_str}", file=sys.stderr)
        
        if self.verbose and event.metadata:
            result_keys = event.metadata.get("result_keys", [])
            if result_keys:
                print(f"   Outputs: {', '.join(result_keys)}", file=sys.stderr)
    
    def _report_workflow_complete(self, event: ProgressEvent, timestamp: str) -> None:
        """Report workflow completion."""
        duration_str = ""
        if event.timestamp:
            total_duration = (event.timestamp - self.start_time).total_seconds()
            duration_str = f" in {total_duration:.1f}s"
        
        print(f"\n🎉 {timestamp} - {event.message}{duration_str}", file=sys.stderr)
        
        if self.verbose and event.metadata:
            outputs = event.metadata.get("outputs", [])
            if outputs:
                print(f"   Final outputs: {', '.join(outputs)}", file=sys.stderr)
    
    def _report_prompt_start(self, event: ProgressEvent, timestamp: str) -> None:
        """Report prompt start (verbose mode only)."""
        if self.verbose:
            print(f"⏳ {timestamp} - {event.message}", file=sys.stderr)
    
    def _report_prompt_complete(self, event: ProgressEvent, timestamp: str) -> None:
        """Report prompt completion (verbose mode only)."""
        if self.verbose:
            duration_str = ""
            if self.last_step_time and event.timestamp:
                duration = (event.timestamp - self.last_step_time).total_seconds()
                duration_str = f" ({duration:.1f}s)"
            print(f"✅ {timestamp} - {event.message}{duration_str}", file=sys.stderr)
    
    def _report_api_request_start(self, event: ProgressEvent, timestamp: str) -> None:
        """Report API request start (verbose mode only)."""
        if self.verbose:
            files_info = ""
            if event.metadata:
                files_count = event.metadata.get("files_count", 0)
                if files_count > 0:
                    files_info = f" (with {files_count} files)"
            print(f"🌐 {timestamp} - Making API request{files_info}", file=sys.stderr)
    
    def _report_api_request_complete(self, event: ProgressEvent, timestamp: str) -> None:
        """Report API request completion (verbose mode only)."""
        if self.verbose:
            response_info = ""
            if event.metadata:
                response_length = event.metadata.get("response_length", 0)
                if response_length > 0:
                    response_info = f" ({response_length} chars)"
            print(f"📡 {timestamp} - API request completed{response_info}", file=sys.stderr)
    
    def _report_error(self, event: ProgressEvent, timestamp: str) -> None:
        """Report error events."""
        print(f"❌ {timestamp} - {event.message}", file=sys.stderr)
        
        if self.verbose and event.metadata:
            error_type = event.metadata.get("error_type")
            if error_type:
                print(f"   Error type: {error_type}", file=sys.stderr)


class StreamingProgressReporter:
    """
    Progress reporter with animated spinner for long-running operations.
    
    This reporter shows a spinning animation to indicate that work is in progress,
    useful for operations that might take a while without intermediate updates.
    """
    
    def __init__(self, verbose: bool = False):
        """
        Initialize the streaming progress reporter.
        
        Args:
            verbose: Show detailed messages along with spinner
        """
        self.verbose = verbose
        self.current_message = ""
        self.spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.spinner_index = 0
        self.last_update = time.time()
        
    def report(self, event: ProgressEvent) -> None:
        """Handle progress events with animated feedback."""
        # Update every 0.1 seconds for smooth animation
        now = time.time()
        if now - self.last_update < 0.1:
            return
            
        self.last_update = now
        timestamp = event.timestamp.strftime("%H:%M:%S") if event.timestamp else "??:??:??"
        
        if event.type in (ProgressType.PROMPT_START, ProgressType.API_REQUEST_START):
            self.current_message = event.message
            self._show_spinner()
        elif event.type in (
            ProgressType.PROMPT_COMPLETE,
            ProgressType.API_REQUEST_COMPLETE,
            ProgressType.WORKFLOW_STEP_COMPLETE
        ):
            self._clear_spinner()
            if self.verbose:
                print(f"✅ {timestamp} - {event.message}")
        elif event.type in (ProgressType.PROMPT_ERROR, ProgressType.WORKFLOW_ERROR):
            self._clear_spinner()
            print(f"❌ {timestamp} - {event.message}", file=sys.stderr)
        elif event.type == ProgressType.WORKFLOW_START:
            print(f"🚀 {timestamp} - {event.message}")
        elif event.type == ProgressType.WORKFLOW_COMPLETE:
            print(f"🎉 {timestamp} - {event.message}")
    
    def _show_spinner(self) -> None:
        """Display animated spinner with current message."""
        if self.current_message:
            spinner = self.spinner_chars[self.spinner_index]
            self.spinner_index = (self.spinner_index + 1) % len(self.spinner_chars)
            
            # Clear line and show spinner
            sys.stderr.write(f'\r{spinner} {self.current_message}')
            sys.stderr.flush()
    
    def _clear_spinner(self) -> None:
        """Clear the spinner line."""
        sys.stderr.write('\r' + ' ' * 80 + '\r')  # Clear line
        sys.stderr.flush()


def create_cli_reporter(verbose: bool = False, quiet: bool = False, streaming: bool = False) -> CLIProgressReporter | StreamingProgressReporter:
    """
    Factory function to create appropriate CLI progress reporter.
    
    Args:
        verbose: Show detailed progress information
        quiet: Suppress all output except errors
        streaming: Use animated progress reporter
        
    Returns:
        Progress reporter instance
    """
    if streaming:
        return StreamingProgressReporter(verbose=verbose)
    else:
        return CLIProgressReporter(verbose=verbose, quiet=quiet)