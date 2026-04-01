"""History compaction for Orac agents.

Replaces older messages with an LLM-generated summary while keeping recent
messages intact for prefix-cache friendliness. Summarization uses a
configurable model via the same call_api() path as the agent.

Two triggers fire compaction:
1. Message count exceeds a threshold (default 12).
2. Time since last message exceeds a gap (default 5 minutes) and there are
   enough messages to make summarization worthwhile.

When triggered, messages older than keep_recent are summarized into a single
user message with [CONVERSATION SUMMARY] markers, preserving the most recent
messages verbatim so downstream prefix caching is minimally disrupted.
"""

from datetime import datetime
from typing import List, Dict, Optional

from .openai_client import call_api, CompletionResult
from .providers import ProviderRegistry
from .config import Provider
from .logger import logger


SUMMARIZATION_SYSTEM_PROMPT = (
    "You are a conversation summarizer. Produce a concise summary of the "
    "conversation below.\n"
    "Preserve:\n"
    "- Key decisions and reasoning\n"
    "- Tool call results and their outcomes\n"
    "- Important facts and data discovered\n"
    "- The current state and goal of the task\n"
    "- Any errors or failures that occurred\n\n"
    "Be factual and concise. Do not add interpretation. Output only the summary text."
)


def format_summary_message(summary_text: str) -> Dict[str, str]:
    """Wrap a summary string in the standard message dict with markers."""
    return {
        "role": "user",
        "text": f"[CONVERSATION SUMMARY]\n\n{summary_text}\n\n[END SUMMARY]",
    }


def _messages_to_text(messages: List[Dict[str, str]]) -> str:
    """Convert a list of message dicts into readable text for the summarizer."""
    lines = []
    for msg in messages:
        role_label = "User" if msg["role"] == "user" else "Assistant"
        lines.append(f"{role_label}: {msg['text']}")
    return "\n\n".join(lines)


def summarize_messages(
    messages: List[Dict[str, str]],
    provider_registry: ProviderRegistry,
    provider: Optional[Provider] = None,
    model_name: str = "gemini-2.0-flash",
) -> str:
    """Call the LLM to produce a summary of the given messages.

    Args:
        messages: The messages to summarize.
        provider_registry: Registry for API access.
        provider: Provider to use for the summarization call.
        model_name: Model to use (should be cheap/fast).

    Returns:
        Summary text string.
    """
    conversation_text = _messages_to_text(messages)
    user_prompt = (
        "Summarize the following conversation history:\n\n" + conversation_text
    )

    result: CompletionResult = call_api(
        provider_registry=provider_registry,
        provider=provider,
        message_history=[{"role": "user", "text": user_prompt}],
        system_prompt=SUMMARIZATION_SYSTEM_PROMPT,
        model_name=model_name,
        generation_config={"temperature": 0.0, "max_tokens": 1024},
    )
    logger.info(
        f"Compaction summarized {len(messages)} messages "
        f"into {len(result.text)} chars"
    )
    return result.text


def maybe_compact(
    message_history: List[Dict[str, str]],
    provider_registry: ProviderRegistry,
    provider: Optional[Provider] = None,
    model_name: str = "gemini-2.0-flash",
    compact_after_messages: int = 12,
    compact_keep_recent: int = 4,
    last_message_time: Optional[datetime] = None,
    compact_time_gap_seconds: int = 300,
) -> List[Dict[str, str]]:
    """Check if compaction is needed and perform it if so.

    Compaction triggers when EITHER:
    - Message count exceeds compact_after_messages, OR
    - Time since last_message_time exceeds compact_time_gap_seconds
      (and there are enough messages to make summarization worthwhile)

    When triggered, messages older than compact_keep_recent are summarized
    and replaced with a single summary message at the start of history.

    Args:
        message_history: Current message list (modified in place and returned).
        provider_registry: For making the summarization API call.
        provider: Provider for the summarization call.
        model_name: Model for summarization.
        compact_after_messages: Message count threshold.
        compact_keep_recent: Number of recent messages to preserve.
        last_message_time: Timestamp of the last message (for time-gap trigger).
        compact_time_gap_seconds: Seconds of idle before time-triggered compaction.

    Returns:
        The (possibly compacted) message history list.
    """
    total = len(message_history)

    count_trigger = total > compact_after_messages
    time_trigger = False
    if last_message_time is not None and total > compact_keep_recent + 1:
        gap = (datetime.now() - last_message_time).total_seconds()
        time_trigger = gap > compact_time_gap_seconds

    if not (count_trigger or time_trigger):
        return message_history

    split_point = total - compact_keep_recent
    if split_point <= 1:
        return message_history

    old_messages = message_history[:split_point]
    recent_messages = message_history[split_point:]

    # Separate pinned from unpinned in old messages
    pinned_messages = [m for m in old_messages if m.get("pinned")]
    unpinned_messages = [m for m in old_messages if not m.get("pinned")]

    trigger_reason = "message count" if count_trigger else "time gap"
    logger.info(
        f"Compacting history ({trigger_reason}): "
        f"{len(old_messages)} old ({len(pinned_messages)} pinned) + "
        f"{len(recent_messages)} recent"
    )

    if not unpinned_messages:
        return message_history

    try:
        summary_text = summarize_messages(
            unpinned_messages,
            provider_registry=provider_registry,
            provider=provider,
            model_name=model_name,
        )
        summary_msg = format_summary_message(summary_text)

        message_history.clear()
        message_history.extend(pinned_messages + [summary_msg] + recent_messages)
        logger.info(
            f"Compacted history from {total} to {len(message_history)} messages "
            f"({len(pinned_messages)} pinned preserved)"
        )
    except Exception as e:
        logger.warning(f"Compaction failed, keeping original history: {e}")

    return message_history
