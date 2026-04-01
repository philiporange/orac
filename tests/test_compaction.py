"""Tests for history compaction in orac/compaction.py.

Covers compaction trigger logic (count-based and time-based), message
formatting, recent message preservation, and graceful failure on API errors.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from orac.compaction import (
    format_summary_message,
    _messages_to_text,
    summarize_messages,
    maybe_compact,
)
from orac.agent import Agent, AgentSpec
from orac.openai_client import CompletionResult


def _make_history(n: int) -> list:
    """Generate n alternating user/model messages."""
    history = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "model"
        history.append({"role": role, "text": f"Message {i}"})
    return history


# ── format_summary_message ──────────────────────────────────────────


class TestFormatSummaryMessage:
    def test_wraps_with_markers(self):
        msg = format_summary_message("test summary")
        assert msg["role"] == "user"
        assert "[CONVERSATION SUMMARY]" in msg["text"]
        assert "test summary" in msg["text"]
        assert "[END SUMMARY]" in msg["text"]

    def test_empty_summary(self):
        msg = format_summary_message("")
        assert msg["role"] == "user"
        assert "[CONVERSATION SUMMARY]" in msg["text"]


# ── _messages_to_text ───────────────────────────────────────────────


class TestMessagesToText:
    def test_converts_roles(self):
        messages = [
            {"role": "user", "text": "hello"},
            {"role": "model", "text": "hi there"},
        ]
        text = _messages_to_text(messages)
        assert "User: hello" in text
        assert "Assistant: hi there" in text

    def test_empty_list(self):
        assert _messages_to_text([]) == ""

    def test_single_message(self):
        text = _messages_to_text([{"role": "user", "text": "only one"}])
        assert text == "User: only one"


# ── maybe_compact ───────────────────────────────────────────────────


class TestMaybeCompact:
    @patch("orac.compaction.summarize_messages")
    def test_no_compaction_below_threshold(self, mock_summarize):
        history = _make_history(5)
        result = maybe_compact(
            history,
            provider_registry=MagicMock(),
            compact_after_messages=12,
            compact_keep_recent=4,
        )
        mock_summarize.assert_not_called()
        assert len(result) == 5

    @patch("orac.compaction.summarize_messages")
    def test_compaction_above_threshold(self, mock_summarize):
        mock_summarize.return_value = "Summary of old messages"
        history = _make_history(15)
        result = maybe_compact(
            history,
            provider_registry=MagicMock(),
            compact_after_messages=12,
            compact_keep_recent=4,
        )
        mock_summarize.assert_called_once()
        # 1 summary + 4 recent = 5
        assert len(result) == 5
        assert "[CONVERSATION SUMMARY]" in result[0]["text"]

    @patch("orac.compaction.summarize_messages")
    def test_keeps_recent_messages_verbatim(self, mock_summarize):
        mock_summarize.return_value = "Summary"
        history = _make_history(15)
        original_recent = [msg["text"] for msg in history[-4:]]
        maybe_compact(
            history,
            provider_registry=MagicMock(),
            compact_after_messages=12,
            compact_keep_recent=4,
        )
        actual_recent = [msg["text"] for msg in history[1:]]
        assert actual_recent == original_recent

    @patch("orac.compaction.summarize_messages")
    def test_time_gap_trigger(self, mock_summarize):
        mock_summarize.return_value = "Summary"
        history = _make_history(8)  # Below count threshold of 12
        old_time = datetime.now() - timedelta(minutes=10)
        result = maybe_compact(
            history,
            provider_registry=MagicMock(),
            compact_after_messages=12,
            compact_keep_recent=4,
            last_message_time=old_time,
            compact_time_gap_seconds=300,
        )
        mock_summarize.assert_called_once()
        assert len(result) == 5  # 1 summary + 4 recent

    @patch("orac.compaction.summarize_messages")
    def test_no_time_trigger_when_recent(self, mock_summarize):
        history = _make_history(8)
        recent_time = datetime.now() - timedelta(seconds=30)
        result = maybe_compact(
            history,
            provider_registry=MagicMock(),
            compact_after_messages=12,
            compact_keep_recent=4,
            last_message_time=recent_time,
            compact_time_gap_seconds=300,
        )
        mock_summarize.assert_not_called()
        assert len(result) == 8

    @patch("orac.compaction.summarize_messages")
    def test_graceful_failure(self, mock_summarize):
        mock_summarize.side_effect = Exception("API error")
        history = _make_history(15)
        original_len = len(history)
        result = maybe_compact(
            history,
            provider_registry=MagicMock(),
            compact_after_messages=12,
            compact_keep_recent=4,
        )
        # History unchanged on failure
        assert len(result) == original_len

    @patch("orac.compaction.summarize_messages")
    def test_modifies_list_in_place(self, mock_summarize):
        mock_summarize.return_value = "Summary"
        history = _make_history(15)
        result = maybe_compact(
            history,
            provider_registry=MagicMock(),
            compact_after_messages=12,
            compact_keep_recent=4,
        )
        # result IS the same list object
        assert result is history
        assert len(history) == 5

    @patch("orac.compaction.summarize_messages")
    def test_too_few_old_messages_skips(self, mock_summarize):
        """If split_point <= 1, don't bother summarizing."""
        history = _make_history(5)
        maybe_compact(
            history,
            provider_registry=MagicMock(),
            compact_after_messages=3,
            compact_keep_recent=4,
        )
        mock_summarize.assert_not_called()


# ── summarize_messages ──────────────────────────────────────────────


class TestSummarizeMessages:
    @patch("orac.compaction.call_api")
    def test_calls_api_with_correct_params(self, mock_call_api):
        mock_call_api.return_value = CompletionResult(text="A summary")
        messages = _make_history(5)
        registry = MagicMock()

        result = summarize_messages(
            messages,
            provider_registry=registry,
            model_name="gemini-2.0-flash",
        )

        assert result == "A summary"
        mock_call_api.assert_called_once()
        call_kwargs = mock_call_api.call_args
        assert call_kwargs.kwargs["model_name"] == "gemini-2.0-flash"
        assert call_kwargs.kwargs["generation_config"]["temperature"] == 0.0


# ── Agent._extract_json ─────────────────────────────────────────────


class TestExtractJson:
    def test_plain_json(self):
        data = Agent._extract_json('{"tool": "test", "thought": "hi"}')
        assert data["tool"] == "test"

    def test_markdown_fenced_json(self):
        text = '```json\n{"tool": "test", "thought": "hi"}\n```'
        data = Agent._extract_json(text)
        assert data["tool"] == "test"

    def test_markdown_fenced_no_lang(self):
        text = '```\n{"tool": "test"}\n```'
        data = Agent._extract_json(text)
        assert data["tool"] == "test"

    def test_surrounding_whitespace(self):
        text = '  \n {"tool": "test"} \n  '
        data = Agent._extract_json(text)
        assert data["tool"] == "test"

    def test_invalid_json_raises(self):
        with pytest.raises(Exception):
            Agent._extract_json("not json at all")


# ── Pinned message compaction ──────────────────────────────────────


class TestPinnedCompaction:
    @patch("orac.compaction.summarize_messages")
    def test_pinned_messages_survive_compaction(self, mock_summarize):
        mock_summarize.return_value = "Summary of unpinned"
        history = _make_history(15)
        # Pin two messages in the old section (will be before split_point)
        history[1]["pinned"] = True
        history[3]["pinned"] = True

        maybe_compact(
            history,
            provider_registry=MagicMock(),
            compact_after_messages=12,
            compact_keep_recent=4,
        )
        # Pinned messages should be at the front
        pinned = [m for m in history if m.get("pinned")]
        assert len(pinned) == 2
        assert history[0]["pinned"] is True
        assert history[1]["pinned"] is True

    @patch("orac.compaction.summarize_messages")
    def test_only_unpinned_are_summarized(self, mock_summarize):
        mock_summarize.return_value = "Summary"
        history = _make_history(15)
        history[2]["pinned"] = True  # Pin one old message

        maybe_compact(
            history,
            provider_registry=MagicMock(),
            compact_after_messages=12,
            compact_keep_recent=4,
        )
        # summarize_messages should have received only unpinned old messages
        call_args = mock_summarize.call_args
        summarized_msgs = call_args[0][0]
        for msg in summarized_msgs:
            assert not msg.get("pinned")

    @patch("orac.compaction.summarize_messages")
    def test_all_pinned_skips_summarization(self, mock_summarize):
        history = _make_history(15)
        # Pin ALL old messages (indices 0-10, since keep_recent=4 means split at 11)
        for i in range(11):
            history[i]["pinned"] = True

        original_len = len(history)
        maybe_compact(
            history,
            provider_registry=MagicMock(),
            compact_after_messages=12,
            compact_keep_recent=4,
        )
        # No summarization should occur since all old messages are pinned
        mock_summarize.assert_not_called()
        assert len(history) == original_len

    @patch("orac.compaction.summarize_messages")
    def test_pinned_order_preserved(self, mock_summarize):
        """Pinned msgs come first, then summary, then recent."""
        mock_summarize.return_value = "Summary"
        history = _make_history(15)
        history[0]["pinned"] = True
        history[4]["pinned"] = True

        recent_texts = [m["text"] for m in history[-4:]]

        maybe_compact(
            history,
            provider_registry=MagicMock(),
            compact_after_messages=12,
            compact_keep_recent=4,
        )
        # Structure: [pinned0, pinned4, summary, recent0..3]
        assert history[0].get("pinned") is True
        assert history[1].get("pinned") is True
        assert "[CONVERSATION SUMMARY]" in history[2]["text"]
        assert [m["text"] for m in history[3:]] == recent_texts
