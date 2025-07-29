"""
Progress tracking infrastructure for Orac operations.

This module provides a callback-based progress tracking system that allows
users to monitor the execution of prompts and flows without affecting
the core functionality.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Callable, Any, Dict


class ProgressType(Enum):
    """Types of progress events that can be emitted during operations."""
    
    # Single prompt events
    PROMPT_START = "prompt_start"
    PROMPT_COMPLETE = "prompt_complete" 
    PROMPT_ERROR = "prompt_error"
    
    # Flow events
    FLOW_START = "flow_start"
    FLOW_STEP_START = "flow_step_start"
    FLOW_STEP_COMPLETE = "flow_step_complete"
    FLOW_COMPLETE = "flow_complete"
    FLOW_ERROR = "flow_error"
    
    # API and file operation events
    API_REQUEST_START = "api_request_start"
    API_REQUEST_COMPLETE = "api_request_complete"
    FILE_UPLOAD_START = "file_upload_start"
    FILE_UPLOAD_COMPLETE = "file_upload_complete"


@dataclass
class ProgressEvent:
    """
    Represents a progress event during operation execution.
    
    Attributes:
        type: The type of progress event
        message: Human-readable description of the event
        current_step: Current step number (1-indexed, optional)
        total_steps: Total number of steps (optional)
        step_name: Name of the current step (optional)
        metadata: Additional data specific to the event type (optional)
        timestamp: When the event occurred (auto-populated)
    """
    type: ProgressType
    message: str
    current_step: Optional[int] = None
    total_steps: Optional[int] = None
    step_name: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        """Auto-populate timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    @property
    def progress_percentage(self) -> Optional[float]:
        """Calculate progress percentage if step information is available."""
        if self.current_step is not None and self.total_steps is not None and self.total_steps > 0:
            return (self.current_step / self.total_steps) * 100
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the event to a dictionary for serialization."""
        return {
            "type": self.type.value,
            "message": self.message,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "step_name": self.step_name,
            "metadata": self.metadata or {},
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "progress_percentage": self.progress_percentage
        }


# Type alias for progress callback functions
ProgressCallback = Callable[[ProgressEvent], None]


class ProgressTracker:
    """
    A utility class for tracking and aggregating progress events.
    
    This can be used to collect progress information programmatically
    instead of just displaying it to the user.
    """
    
    def __init__(self):
        self.events: list[ProgressEvent] = []
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
    
    def track(self, event: ProgressEvent) -> None:
        """Record a progress event."""
        if self.start_time is None:
            self.start_time = event.timestamp
        
        self.events.append(event)
        
        # Update end time for completion/error events
        if event.type in (
            ProgressType.PROMPT_COMPLETE,
            ProgressType.PROMPT_ERROR,
            ProgressType.FLOW_COMPLETE,
            ProgressType.FLOW_ERROR
        ):
            self.end_time = event.timestamp
    
    @property
    def duration(self) -> Optional[float]:
        """Get the total duration in seconds, if available."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None
    
    @property
    def current_progress(self) -> Optional[ProgressEvent]:
        """Get the most recent progress event."""
        return self.events[-1] if self.events else None
    
    def get_events_by_type(self, event_type: ProgressType) -> list[ProgressEvent]:
        """Get all events of a specific type."""
        return [event for event in self.events if event.type == event_type]
    
    def to_summary(self) -> Dict[str, Any]:
        """Generate a summary of the tracked progress."""
        if not self.events:
            return {"status": "no_events", "events": []}
        
        first_event = self.events[0]
        last_event = self.events[-1]
        
        # Determine overall status
        if any(event.type.value.endswith("_error") for event in self.events):
            status = "error"
        elif any(event.type.value.endswith("_complete") for event in self.events):
            status = "complete"  
        else:
            status = "in_progress"
        
        return {
            "status": status,
            "start_time": first_event.timestamp.isoformat() if first_event.timestamp else None,
            "end_time": last_event.timestamp.isoformat() if last_event.timestamp else None,
            "duration_seconds": self.duration,
            "total_events": len(self.events),
            "events": [event.to_dict() for event in self.events]
        }


def create_simple_callback(verbose: bool = False) -> ProgressCallback:
    """
    Create a simple progress callback that prints to stdout.
    
    Args:
        verbose: If True, shows all events. If False, only shows major milestones.
    
    Returns:
        A progress callback function
    """
    def callback(event: ProgressEvent) -> None:
        timestamp = event.timestamp.strftime("%H:%M:%S") if event.timestamp else "??:??:??"
        
        if event.type == ProgressType.FLOW_START:
            print(f"🚀 {timestamp} - {event.message}")
            if event.total_steps:
                print(f"   Total steps: {event.total_steps}")
        
        elif event.type == ProgressType.FLOW_STEP_START:
            if event.current_step and event.total_steps:
                progress = f"[{event.current_step}/{event.total_steps}]"
                print(f"📝 {timestamp} - {progress} {event.message}")
            else:
                print(f"📝 {timestamp} - {event.message}")
        
        elif event.type == ProgressType.FLOW_STEP_COMPLETE:
            print(f"✅ {timestamp} - Step completed: {event.step_name or 'unknown'}")
        
        elif event.type == ProgressType.FLOW_COMPLETE:
            print(f"🎉 {timestamp} - {event.message}")
        
        elif event.type in (ProgressType.PROMPT_ERROR, ProgressType.FLOW_ERROR):
            print(f"❌ {timestamp} - {event.message}")
        
        elif verbose and event.type == ProgressType.PROMPT_START:
            print(f"⏳ {timestamp} - {event.message}")
        
        elif verbose and event.type == ProgressType.PROMPT_COMPLETE:
            print(f"✅ {timestamp} - {event.message}")
    
    return callback