"""Tests for the AgentEvent callback and continue_with refactor.

These tests stub `call_api` and `maybe_compact` at the agent module boundary so
they exercise the ReAct loop deterministically without making real LLM calls.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
import yaml

from orac.agent import Agent, AgentEvent, AgentSpec
from orac.openai_client import CompletionResult
from orac.providers import ProviderRegistry
from orac.registry import ToolRegistry


@pytest.fixture
def registry():
    tmp = tempfile.TemporaryDirectory()
    base = Path(tmp.name)
    (base / "prompts").mkdir()
    (base / "skills").mkdir()
    (base / "skills" / "echo.yaml").write_text(yaml.dump({
        "name": "echo",
        "description": "echoes its input",
    }))
    reg = ToolRegistry(
        prompts_dir=str(base / "prompts"),
        tools_dir=str(base / "skills"),
    )
    yield reg
    tmp.cleanup()


@pytest.fixture
def spec():
    return AgentSpec(
        name="t",
        description="test agent",
        system_prompt="goal=${goal} tools=${tool_list}",
        inputs=[{"name": "goal", "type": "string"}],
        tools=["tool:finish"],
        max_iterations=3,
    )


def _make_agent(spec, registry, callback=None):
    return Agent(
        agent_spec=spec,
        tool_registry=registry,
        provider_registry=ProviderRegistry(),
        event_callback=callback,
    )


def _mock_call_api_returning(monkeypatch, payloads):
    """Patch call_api to return successive JSON payloads as CompletionResult."""
    iterator = iter(payloads)

    def fake_call_api(**kwargs):
        return CompletionResult(text=json.dumps(next(iterator)))

    monkeypatch.setattr("orac.agent.call_api", fake_call_api)
    monkeypatch.setattr("orac.agent.maybe_compact", lambda **kw: None)


def test_event_callback_emits_run_lifecycle(spec, registry, monkeypatch):
    _mock_call_api_returning(monkeypatch, [
        {"thought": "done", "tool": "tool:finish", "inputs": {"result": "42"}},
    ])

    events: list[AgentEvent] = []
    agent = _make_agent(spec, registry, callback=events.append)

    result = agent.run(goal="answer the question")

    assert result == "42"
    types = [e.type for e in events]
    assert types == ["iteration_start", "model_action", "finish"]
    assert events[0].iteration == 1
    assert events[1].payload["action"]["tool"] == "tool:finish"
    assert events[2].payload["result"] == "42"


def test_max_iterations_event(spec, registry, monkeypatch):
    spec.max_iterations = 2
    _mock_call_api_returning(monkeypatch, [
        # Two non-finish actions that just call a missing tool to keep the loop going
        {"thought": "x", "tool": "tool:missing", "inputs": {}},
        {"thought": "y", "tool": "tool:missing", "inputs": {}},
    ])

    events: list[AgentEvent] = []
    agent = _make_agent(spec, registry, callback=events.append)

    result = agent.run(goal="loop forever")

    assert "Maximum iterations" in result
    types = [e.type for e in events]
    assert types.count("iteration_start") == 2
    assert types[-1] == "max_iterations"
    assert events[-1].iteration == 2


def test_invalid_action_event(spec, registry, monkeypatch):
    """Non-JSON model output should emit invalid_action and keep iterating."""
    iterator = iter([
        "this is not json at all",
        json.dumps({"thought": "ok", "tool": "tool:finish", "inputs": {"result": "recovered"}}),
    ])

    def fake_call_api(**kwargs):
        return CompletionResult(text=next(iterator))

    monkeypatch.setattr("orac.agent.call_api", fake_call_api)
    monkeypatch.setattr("orac.agent.maybe_compact", lambda **kw: None)

    events: list[AgentEvent] = []
    agent = _make_agent(spec, registry, callback=events.append)

    result = agent.run(goal="recover")

    assert result == "recovered"
    types = [e.type for e in events]
    assert "invalid_action" in types
    assert types[-1] == "finish"


def test_continue_with_resumes_loop(spec, registry, monkeypatch):
    _mock_call_api_returning(monkeypatch, [
        {"thought": "first", "tool": "tool:finish", "inputs": {"result": "first answer"}},
        {"thought": "second", "tool": "tool:finish", "inputs": {"result": "second answer"}},
    ])

    events: list[AgentEvent] = []
    agent = _make_agent(spec, registry, callback=events.append)

    first = agent.run(goal="initial")
    assert first == "first answer"

    second = agent.continue_with("a follow-up question")
    assert second == "second answer"

    # Verify the follow-up message was recorded in history between turns
    user_messages = [m["text"] for m in agent.message_history if m["role"] == "user"]
    assert any("a follow-up question" in t for t in user_messages)

    # Verify two finish events fired across the two turns
    finish_events = [e for e in events if e.type == "finish"]
    assert len(finish_events) == 2


def test_continue_with_requires_run_first(spec, registry):
    agent = _make_agent(spec, registry)
    with pytest.raises(RuntimeError, match="run\\(\\)"):
        agent.continue_with("hello")


def test_callback_exception_does_not_break_run(spec, registry, monkeypatch):
    _mock_call_api_returning(monkeypatch, [
        {"thought": "go", "tool": "tool:finish", "inputs": {"result": "ok"}},
    ])

    def bad_callback(event):
        raise RuntimeError("callback boom")

    agent = _make_agent(spec, registry, callback=bad_callback)
    # Must not propagate
    assert agent.run(goal="resilience") == "ok"


def test_no_callback_is_a_noop(spec, registry, monkeypatch):
    _mock_call_api_returning(monkeypatch, [
        {"thought": "go", "tool": "tool:finish", "inputs": {"result": "fine"}},
    ])
    agent = _make_agent(spec, registry, callback=None)
    assert agent.run(goal="quiet") == "fine"
