# Orac Self-Improvement Testing Platform

This document describes how to build an Orac-native platform that does what we
just did manually with the TV curator agent: let an LLM play the user, run open
ended conversations against an Orac bot, inspect the resulting dialogue, propose
prompt improvements, apply controlled edits, and iterate.

The goal is not a brittle unit-test substitute. It is a prompt development
workbench that creates realistic pressure on agents: ambiguous followups,
short messages, corrections, long-running tool tasks, inconsistent data sources,
style drift, overlong answers, wrong tool choice, and forgotten context.

## Desired Workflow

The operator should be able to run:

```bash
orac improve run tv_curator \
  --prompt-file .orac/agents/tv_curator.yaml \
  --rounds 5 \
  --conversations 10 \
  --turns 8 \
  --output-dir /tmp/orac-self-improvement/tv_curator
```

The system should:

1. Load the target prompt or agent YAML.
2. Start N simulated conversations using one or more LLM user personas.
3. Let each user persona ask whatever they naturally want, including followups.
4. Run the target bot through the same API/agent path production uses.
5. Record every user message, assistant reply, tool call, observation, error,
   token count, latency, and final outcome.
6. Judge each conversation with another LLM using a structured rubric.
7. Identify repeated defects and likely prompt causes.
8. Generate a proposed prompt patch.
9. Run a regression pass against the previous failure cases.
10. Produce a human-readable report and an optional patch file.

By default, prompt changes should be proposed, not automatically committed. A
separate `--apply` flag can opt into writing the prompt file after the evaluator
has produced a patch and a regression pass has not made the score worse.

## Architectural Fit In Orac

Current Orac pieces this should build on:

- `orac.agent.Agent`: ReAct loop for YAML agents with tools.
- `orac.prompt.Prompt`: prompt runner with conversation support.
- `orac.registry.ToolRegistry`: layered discovery for prompts, flows, skills,
  teams, and agents.
- `orac.conversation_db.ConversationDB`: SQLite conversation storage.
- `orac.openai_client.call_api`: provider-agnostic OpenAI-compatible calls.
- `orac.api`: FastAPI endpoints for prompts, agents, teams, and chat.
- `orac/cli`: command structure for resource-specific CLI commands.

The self-improvement system should live under a new package namespace:

```text
orac/
  self_improvement/
    __init__.py
    models.py
    runner.py
    bot_adapters.py
    user_simulator.py
    evaluator.py
    prompt_editor.py
    storage.py
    report.py
    regression.py
  cli/
    improve.py
```

This keeps the feature separate from core prompt execution while still reusing
Orac's registries, clients, provider configuration, and YAML conventions.

## Core Data Model

Use JSONL for raw artifacts and SQLite for indexed runs. JSONL makes it easy to
inspect and replay; SQLite makes it easy to query failures across runs.

```python
"""
Data structures for Orac's self-improvement harness.

The module defines serializable records for simulated conversations, individual
turns, tool events, evaluator judgments, and prompt patch proposals. These
records are written to JSONL for reproducible replay and mirrored into SQLite
for querying repeated failure patterns across improvement runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal


Role = Literal["simulated_user", "assistant", "tool", "system", "judge"]


@dataclass
class ToolEvent:
    tool_name: str
    inputs: dict[str, Any]
    observation: str
    started_at: datetime
    finished_at: datetime
    error: str | None = None


@dataclass
class DialogueTurn:
    index: int
    role: Role
    content: str
    timestamp: datetime
    tool_events: list[ToolEvent] = field(default_factory=list)
    latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass
class ConversationRun:
    run_id: str
    conversation_id: str
    target_name: str
    target_type: Literal["agent", "prompt", "api"]
    prompt_file: Path | None
    simulator_persona: str
    scenario_seed: str
    turns: list[DialogueTurn]
    started_at: datetime
    finished_at: datetime | None = None


@dataclass
class EvaluationResult:
    conversation_id: str
    overall_score: float
    passed: bool
    defects: list[dict[str, Any]]
    strengths: list[str]
    prompt_diagnosis: list[str]
    suggested_tests: list[str]


@dataclass
class PromptPatchProposal:
    run_id: str
    target_prompt_file: Path
    rationale: str
    unified_diff: str
    expected_effects: list[str]
    risks: list[str]
```

## Capturing Agent Internals

The current `Agent.run()` prints iterations, tool actions, and observations, but
does not expose structured events. The self-improvement harness needs structured
event capture so the evaluator can detect tool misuse and iteration loops.

Add an optional callback to `Agent`.

```python
"""
Agent event capture hooks for self-improvement and debugging.

AgentEvent is emitted by Agent.run whenever the ReAct loop receives a model
action, starts or finishes a tool call, observes an error, compacts history, or
returns a final answer. The core agent remains usable without callbacks; callers
that need telemetry can attach an event sink.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Literal


AgentEventType = Literal[
    "iteration_start",
    "model_action",
    "tool_start",
    "tool_finish",
    "invalid_action",
    "compaction",
    "finish",
    "max_iterations",
]


@dataclass
class AgentEvent:
    type: AgentEventType
    timestamp: datetime
    iteration: int | None = None
    payload: dict[str, Any] | None = None


AgentEventCallback = Callable[[AgentEvent], None]
```

Integration sketch inside `orac/agent.py`:

```python
class Agent:
    def __init__(
        self,
        agent_spec: AgentSpec,
        tool_registry: ToolRegistry,
        provider_registry: ProviderRegistry,
        provider: Optional[Provider] = None,
        event_callback: AgentEventCallback | None = None,
    ):
        self.spec = agent_spec
        self.registry = tool_registry
        self.provider_registry = provider_registry
        self.provider = provider
        self.event_callback = event_callback
        self.message_history = []
        self.total_usage = None
        self.last_message_time = None

    def _emit(self, type: str, iteration: int | None = None, **payload):
        if self.event_callback:
            self.event_callback(AgentEvent(
                type=type,
                timestamp=datetime.now(),
                iteration=iteration,
                payload=payload,
            ))
```

Then emit at key points:

```python
self._emit("iteration_start", i + 1)
self._emit("model_action", i + 1, action=action_data)
self._emit("tool_start", i + 1, tool=tool_name, inputs=tool_inputs)
observation = self._execute_tool(tool_name, tool_inputs)
self._emit("tool_finish", i + 1, tool=tool_name, observation=str(observation))
self._emit("finish", i + 1, result=final_answer)
self._emit("max_iterations", self.spec.max_iterations)
```

This callback should also be used by production API debugging later; it is not
only for self-improvement.

## Bot Adapters

The harness should support multiple target types:

- Direct `Agent` YAML execution.
- Direct `Prompt` YAML execution.
- HTTP API endpoint execution for project-specific bots such as the TV frontend.

Use a small adapter interface.

```python
"""
Bot adapters for the self-improvement harness.

Adapters normalize different Orac execution surfaces into a single chat-like
interface. A simulated user can send one message at a time while adapters decide
whether to invoke an Agent, Prompt, or HTTP API and return a BotReply with
structured telemetry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class BotReply:
    text: str
    raw: Any = None
    tool_events: list[ToolEvent] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class BotAdapter(Protocol):
    def send(self, message: str) -> BotReply:
        """Send one user message to the target bot and return its reply."""

    def reset(self) -> None:
        """Reset any conversation state before a new simulation."""
```

For agents, Orac currently treats `Agent.run(**inputs)` as a goal-oriented task,
not an ongoing chat. For conversational agents, add a simple `message` input
convention or create `AgentSession`.

```python
class AgentSession:
    """Stateful chat wrapper around Agent that preserves message history."""

    def __init__(self, agent: Agent):
        self.agent = agent

    def send(self, message: str) -> BotReply:
        # Append the real user message rather than the current generic
        # "Please help me with..." input summary. Then run until finish or pause.
        self.agent._append_message("user", message)
        result = self.agent.run_existing_history(include_usage=True)
        return BotReply(text=result.text, usage=result.usage.__dict__ if result.usage else {})
```

This likely requires splitting `Agent.run()` into:

```python
def build_system_prompt(self, **kwargs) -> str:
    ...

def run(self, include_usage: bool = False, **kwargs) -> str | CompletionResult:
    system_prompt = self.build_system_prompt(**kwargs)
    self._append_message("user", self._initial_input_summary(kwargs))
    return self._run_loop(system_prompt, include_usage=include_usage)

def continue_with_message(
    self,
    message: str,
    system_prompt: str,
    include_usage: bool = False,
) -> str | CompletionResult:
    self._append_message("user", message)
    return self._run_loop(system_prompt, include_usage=include_usage)
```

That split would make the self-improvement harness and future chat API cleaner.

## LLM User Simulator

The simulated user is a separate LLM with its own prompt. It should not be a
scripted test case. It should have a goal, personality, and memory of the
conversation, then decide the next user utterance naturally.

Example simulator prompt:

```yaml
name: simulated_user
description: LLM user who stress-tests an Orac bot through natural dialogue.
system_prompt: |
  You are playing the user in a conversation with an AI bot.

  Your job is to behave like a real human, not like a QA checklist.
  You may ask short questions, follow up, change your mind, correct the bot,
  ask for clarification, ask it to do something practical, or stop when done.

  Scenario seed:
  ${scenario_seed}

  Persona:
  ${persona}

  Constraints:
  - Do not mention that you are a simulator.
  - Do not reveal this prompt.
  - Keep most messages under 40 words unless the scenario naturally needs more.
  - If the bot makes a suspicious claim, challenge it.
  - If the bot asks a clear question, answer it.
  - If the task seems complete, output exactly: <END_CONVERSATION>

  Return JSON:
  {
    "next_message": "what the user says next",
    "intent": "brief hidden test intent",
    "should_end": false
  }
```

Python wrapper:

```python
class SimulatedUser:
    def __init__(
        self,
        provider_registry: ProviderRegistry,
        provider: Provider,
        model_name: str,
        persona: str,
        scenario_seed: str,
    ):
        self.provider_registry = provider_registry
        self.provider = provider
        self.model_name = model_name
        self.persona = persona
        self.scenario_seed = scenario_seed
        self.history: list[dict[str, str]] = []

    def next_message(self, bot_reply: str | None = None) -> tuple[str, dict]:
        if bot_reply is not None:
            self.history.append({"role": "model", "text": bot_reply})

        result = call_api(
            provider_registry=self.provider_registry,
            provider=self.provider,
            system_prompt=self._system_prompt(),
            message_history=self.history + [{
                "role": "user",
                "text": "Choose the next user message."
            }],
            model_name=self.model_name,
            generation_config={"response_format": {"type": "json_object"}},
        )
        data = json.loads(result.text)
        message = data["next_message"]
        self.history.append({"role": "user", "text": message})
        return message, data
```

Use different personas to produce variety:

```python
DEFAULT_PERSONAS = [
    "A busy user who writes terse messages and expects direct answers.",
    "A skeptical user who challenges availability, citations, and assumptions.",
    "A meandering user who changes requirements halfway through.",
    "A novice who does not know the domain vocabulary.",
    "A power user who expects the bot to use tools without being told.",
    "A user who asks one-word or two-word followups.",
]
```

## Scenario Generation

The platform needs scenario seeds, but the simulated user should remain free to
improvise. For a TV/movie bot, a seed might be: “Find a movie, check if it is
available, add it if missing, then follow progress.” For a research bot:
“Ask for current information, then ask for source quality.”

Generic scenario generator:

```python
def generate_scenarios(
    target_description: str,
    tools_spec: str,
    count: int,
    provider_registry: ProviderRegistry,
    provider: Provider,
) -> list[str]:
    system_prompt = """
    Generate realistic user scenario seeds for testing an AI bot.
    The scenarios should be diverse, practical, and likely to expose prompt,
    tool-use, context-retention, verbosity, and recovery failures.
    Return JSON: {"scenarios": ["...", "..."]}
    """
    result = call_api(
        provider_registry=provider_registry,
        provider=provider,
        system_prompt=system_prompt,
        message_history=[{
            "role": "user",
            "text": f"Bot description:\n{target_description}\n\nTools:\n{tools_spec}\n\nCount: {count}"
        }],
        generation_config={"response_format": {"type": "json_object"}},
    )
    return json.loads(result.text)["scenarios"]
```

Also allow hand-written scenario files for regression suites:

```yaml
target: tv_curator
scenarios:
  - id: terse_greeting
    seed: "Start with a greeting only, then ask for a recommendation."
  - id: movie_context_followup
    seed: "Ask about a movie by title, then refer to it only as 'it'."
  - id: availability_then_add
    seed: "Check if a missing movie is available, ask to add it, then monitor."
```

## Conversation Runner

The runner coordinates simulated user turns and bot replies.

```python
class ImprovementRunner:
    def __init__(
        self,
        bot: BotAdapter,
        simulator_factory: Callable[[str, str], SimulatedUser],
        evaluator: DialogueEvaluator,
        storage: ImprovementStorage,
        max_turns: int,
    ):
        self.bot = bot
        self.simulator_factory = simulator_factory
        self.evaluator = evaluator
        self.storage = storage
        self.max_turns = max_turns

    def run_one(self, scenario_seed: str, persona: str) -> tuple[ConversationRun, EvaluationResult]:
        self.bot.reset()
        user = self.simulator_factory(persona, scenario_seed)
        turns: list[DialogueTurn] = []
        bot_reply_text = None

        for index in range(self.max_turns):
            user_text, user_meta = user.next_message(bot_reply_text)
            if user_text.strip() == "<END_CONVERSATION>" or user_meta.get("should_end"):
                break

            turns.append(DialogueTurn(
                index=len(turns),
                role="simulated_user",
                content=user_text,
                timestamp=datetime.now(),
            ))

            started = monotonic()
            reply = self.bot.send(user_text)
            latency_ms = int((monotonic() - started) * 1000)

            turns.append(DialogueTurn(
                index=len(turns),
                role="assistant",
                content=reply.text,
                timestamp=datetime.now(),
                tool_events=reply.tool_events,
                latency_ms=latency_ms,
                total_tokens=reply.usage.get("total_tokens"),
            ))
            bot_reply_text = reply.text

        conversation = ConversationRun(...)
        evaluation = self.evaluator.evaluate(conversation)
        self.storage.save_conversation(conversation)
        self.storage.save_evaluation(evaluation)
        return conversation, evaluation
```

## Evaluator

The evaluator should be a judge LLM that returns structured JSON. It should
grade both ordinary conversational quality and task-specific behavior.

Core rubric:

- Correctness: claims match tool observations and known state.
- Tool use: used necessary tools, avoided unnecessary tools, preserved media or
  domain type in followups.
- Context retention: understood pronouns, terse followups, and corrections.
- Conversational fit: short replies to short inputs, richer replies when useful.
- Progress handling: reports current state accurately and explains next action.
- Recovery: handles tool errors, ambiguity, and stale caches honestly.
- Style consistency: follows the prompt persona without repetitive templates.
- Safety and scope: avoids overclaiming or performing destructive actions.

Evaluator prompt:

```yaml
name: dialogue_evaluator
system_prompt: |
  You are evaluating a dialogue between a simulated user and an AI bot.
  You are not judging whether the user's goal was convenient. Judge how well the
  bot handled the interaction using the transcript and tool events.

  Return strict JSON:
  {
    "overall_score": 0.0,
    "passed": false,
    "defects": [
      {
        "severity": "critical|major|minor",
        "category": "correctness|tool_use|context|verbosity|style|recovery|other",
        "turn_index": 0,
        "evidence": "quote or paraphrase",
        "why_it_matters": "impact",
        "prompt_root_cause": "likely missing or conflicting instruction",
        "suggested_prompt_change": "specific instruction or example"
      }
    ],
    "strengths": [],
    "prompt_diagnosis": [],
    "suggested_tests": []
  }

  Pay special attention to:
  - The bot saying more than the user asked for.
  - The bot losing context on followups.
  - The bot using the wrong tool or wrong media/resource type.
  - The bot presenting stale tool data as truth.
  - The bot repeating the same response pattern across turns.
```

Evaluator implementation:

```python
class DialogueEvaluator:
    def evaluate(self, conversation: ConversationRun) -> EvaluationResult:
        transcript = render_transcript_for_judge(conversation)
        result = call_api(
            provider_registry=self.provider_registry,
            provider=self.provider,
            system_prompt=self.system_prompt,
            message_history=[{"role": "user", "text": transcript}],
            model_name=self.model_name,
            generation_config={"response_format": {"type": "json_object"}},
        )
        data = json.loads(result.text)
        return EvaluationResult(
            conversation_id=conversation.conversation_id,
            overall_score=float(data["overall_score"]),
            passed=bool(data["passed"]),
            defects=data.get("defects", []),
            strengths=data.get("strengths", []),
            prompt_diagnosis=data.get("prompt_diagnosis", []),
            suggested_tests=data.get("suggested_tests", []),
        )
```

## Prompt Improvement Engine

The improvement engine should aggregate failures across conversations and
generate a patch to the target YAML. It should not rewrite the whole prompt
unless asked; small diffs are easier to review and safer to regress.

Inputs:

- Current prompt file content.
- Top repeated defects by category and severity.
- Representative transcript snippets.
- Tool specs.
- Previous prompt patch history, if available.

Patch-generation prompt:

```yaml
name: prompt_patch_writer
system_prompt: |
  You improve Orac prompt YAML files.

  Produce a minimal unified diff against the provided prompt file.
  Do not rewrite unrelated sections.
  Preserve YAML syntax.
  Prefer adding concrete behavioral rules and few-shot examples for observed
  defects.
  Do not remove tool schemas or required JSON action formats.
  If the safest change is no prompt change, return an empty diff and explain why.

  Return JSON:
  {
    "rationale": "why this patch addresses the failures",
    "unified_diff": "...",
    "expected_effects": ["..."],
    "risks": ["..."]
  }
```

Implementation:

```python
class PromptEditor:
    def propose_patch(
        self,
        prompt_file: Path,
        evaluations: list[EvaluationResult],
        conversations: list[ConversationRun],
    ) -> PromptPatchProposal:
        prompt_text = prompt_file.read_text()
        failure_brief = build_failure_brief(evaluations, conversations)

        result = call_api(
            provider_registry=self.provider_registry,
            provider=self.provider,
            system_prompt=self.patch_writer_prompt,
            message_history=[{
                "role": "user",
                "text": (
                    f"Prompt file: {prompt_file}\n\n"
                    f"Current content:\n```yaml\n{prompt_text}\n```\n\n"
                    f"Observed failures:\n{failure_brief}\n"
                )
            }],
            generation_config={"response_format": {"type": "json_object"}},
        )
        data = json.loads(result.text)
        return PromptPatchProposal(
            run_id=self.run_id,
            target_prompt_file=prompt_file,
            rationale=data["rationale"],
            unified_diff=data["unified_diff"],
            expected_effects=data.get("expected_effects", []),
            risks=data.get("risks", []),
        )
```

Patch application should use a real unified diff parser or `git apply --check`
before writing.

```python
def validate_patch(repo_root: Path, diff_text: str) -> None:
    proc = subprocess.run(
        ["git", "apply", "--check", "-"],
        cwd=repo_root,
        input=diff_text,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise ValueError(proc.stderr)


def apply_patch(repo_root: Path, diff_text: str) -> None:
    validate_patch(repo_root, diff_text)
    subprocess.run(
        ["git", "apply", "-"],
        cwd=repo_root,
        input=diff_text,
        text=True,
        check=True,
    )
```

## Regression Pass

After a proposed patch, run a smaller suite against:

- Any failed scenario seeds from the previous round.
- Any evaluator-suggested regression tests.
- A few previously passing conversations to catch regressions.
- Baseline sanity scenarios such as “Hi” and short followups.

Regression comparison:

```python
def compare_rounds(before: list[EvaluationResult], after: list[EvaluationResult]) -> dict:
    before_score = sum(r.overall_score for r in before) / max(len(before), 1)
    after_score = sum(r.overall_score for r in after) / max(len(after), 1)

    critical_before = sum(
        1 for r in before for d in r.defects if d.get("severity") == "critical"
    )
    critical_after = sum(
        1 for r in after for d in r.defects if d.get("severity") == "critical"
    )

    return {
        "before_score": before_score,
        "after_score": after_score,
        "score_delta": after_score - before_score,
        "critical_before": critical_before,
        "critical_after": critical_after,
        "accepted": after_score >= before_score and critical_after <= critical_before,
    }
```

Only apply automatically when:

- `--apply` is passed.
- YAML parses.
- `git apply --check` passes.
- Regression score does not drop.
- Critical defects do not increase.

## Storage Layout

Use `/tmp/orac-self-improvement/<target>/<run_id>` by default.

```text
/tmp/orac-self-improvement/tv_curator/20260425-191500/
  config.json
  prompt.before.yaml
  prompt.after.yaml
  conversations.jsonl
  evaluations.jsonl
  proposed.patch
  report.md
  regression/
    conversations.jsonl
    evaluations.jsonl
```

SQLite can sit beside these artifacts:

```sql
CREATE TABLE runs (
  id TEXT PRIMARY KEY,
  target_name TEXT NOT NULL,
  target_type TEXT NOT NULL,
  prompt_file TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  config_json TEXT NOT NULL
);

CREATE TABLE conversations (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  scenario_seed TEXT NOT NULL,
  persona TEXT NOT NULL,
  transcript_json TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES runs(id)
);

CREATE TABLE evaluations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id TEXT NOT NULL,
  overall_score REAL NOT NULL,
  passed INTEGER NOT NULL,
  defects_json TEXT NOT NULL,
  FOREIGN KEY(conversation_id) REFERENCES conversations(id)
);

CREATE TABLE prompt_patches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  prompt_file TEXT NOT NULL,
  rationale TEXT NOT NULL,
  unified_diff TEXT NOT NULL,
  accepted INTEGER DEFAULT 0,
  FOREIGN KEY(run_id) REFERENCES runs(id)
);
```

## CLI Surface

Add `orac/cli/improve.py` and register it from `orac/cli/main.py`.

Commands:

```bash
orac improve run <target>
orac improve report <run-id>
orac improve replay <conversation-id>
orac improve patch <run-id> --apply
orac improve list
```

Example parser structure:

```python
"""
CLI commands for Orac self-improvement runs.

The improve command launches simulated user conversations against a target bot,
evaluates the transcripts, proposes prompt patches, and can replay or report on
previous runs.
"""

class ImproveCommand(ResourceCommand):
    name = "improve"
    help_text = "Run LLM-driven prompt self-improvement experiments"
    description = "Simulate users, evaluate dialogues, and propose prompt patches"

    actions = {
        "run": {
            "help": "Run a self-improvement experiment",
            "args": ["target"],
            "handler": "run",
        },
        "report": {
            "help": "Render a report for a run",
            "args": ["run_id"],
            "handler": "report",
        },
        "replay": {
            "help": "Print a stored conversation transcript",
            "args": ["conversation_id"],
            "handler": "replay",
        },
        "patch": {
            "help": "Apply a proposed prompt patch",
            "args": ["run_id"],
            "handler": "patch",
        },
    }
```

Run options:

```text
--target-type agent|prompt|api
--prompt-file PATH
--api-url URL
--provider PROVIDER
--model MODEL
--simulator-model MODEL
--judge-model MODEL
--rounds INT
--conversations INT
--turns INT
--scenario-file PATH
--output-dir PATH
--apply
--seed TEXT
```

## Report Format

The generated `report.md` should be written for prompt maintainers.

```markdown
# Self-Improvement Report: tv_curator

Run: 20260425-191500
Prompt: .orac/agents/tv_curator.yaml

## Summary

- Conversations: 10
- Passed: 7
- Average score: 0.81
- Critical defects: 0
- Major defects: 4

## Repeated Patterns

1. Lost movie context after terse followups.
2. Reported stale Auto TV cache as Jellyfin truth.
3. Over-answered short greetings.

## Proposed Prompt Patch

Rationale...

```diff
...
```

## Representative Failures

### Conversation 4

User: Check Apex again.
Assistant: ...
Judge: The assistant switched to TV search despite prior movie context.
```

## Prompt Improvement Patterns

The patch writer should know common prompt repair moves:

- Add “short input, short reply” rules.
- Add followup context rules, especially preserving entity type and prior task.
- Add tool sequencing examples.
- Add stale data handling instructions.
- Add “when sources disagree, say so” rules.
- Add few-shot examples for fragile flows.
- Remove or soften style rules that cause repetitive templates.
- Add explicit stop conditions for agents that hit maximum iterations.

The evaluator should classify defects into these prompt-repair buckets so patch
generation can be more reliable.

## Guardrails

This system can easily overfit prompts. Use these controls:

- Keep raw conversations and patches inspectable.
- Prefer minimal diffs.
- Run regression before accepting a patch.
- Track score trend over multiple runs.
- Never let the prompt editor remove safety, tool schemas, or required output
  formats.
- Never apply patches when YAML parsing fails.
- Preserve unrelated user changes in the working tree.
- Use `/tmp/orac-self-improvement` for generated artifacts by default.

## Minimal First Milestone

Build the smallest useful vertical slice:

1. Add `AgentEvent` callback support.
2. Add `BotAdapter` for HTTP API targets.
3. Add `SimulatedUser`.
4. Add `DialogueEvaluator`.
5. Add JSONL storage.
6. Add `orac improve run --target-type api`.
7. Generate `report.md` and `proposed.patch`, but do not apply patches.

This first milestone would already reproduce the manual TV-curator workflow:
simulate a user asking whether a movie exists, ask to add it, monitor progress,
judge the dialogue, and suggest prompt edits for failures.

## Second Milestone

Make it Orac-native:

1. Add `AgentSession` or split `Agent.run()` into reusable loop methods.
2. Add `BotAdapter` for direct `Agent` YAML targets.
3. Add scenario files.
4. Add regression replay.
5. Add `orac improve patch --apply`.
6. Add SQLite indexing and `orac improve list`.

## Tests

Add absolute-minimal tests under `tests/` as features land.

Suggested unit tests:

```python
def test_render_transcript_for_judge_includes_tool_events():
    ...


def test_jsonl_storage_round_trips_conversation(tmp_path):
    ...


def test_regression_comparison_rejects_new_critical_defect():
    ...


def test_prompt_patch_validation_rejects_invalid_diff(tmp_path):
    ...
```

Mock LLM calls for unit tests. Keep one optional external integration test behind
an environment flag:

```bash
ORAC_RUN_EXTERNAL_SELF_IMPROVEMENT_TESTS=1 pytest tests/test_self_improvement_external.py
```

## Open Design Questions

- Should `Agent` become truly conversational, or should conversational bots be
  represented as prompts/API targets only?
- Should prompt patches be generated as unified diffs, structured YAML edits, or
  both?
- Should the evaluator use one judge model or a panel of cheaper judges?
- Should simulated users have access to hidden ground truth fixtures for
  domains like media availability?
- Should long-running tool tasks support wait/poll policies inside the harness
  instead of relying entirely on the bot?

## Recommended Implementation Order

1. Implement event capture in `Agent`.
2. Implement JSONL storage and transcript rendering.
3. Implement HTTP API `BotAdapter`.
4. Implement simulated user and evaluator prompts.
5. Add `orac improve run` for API targets.
6. Add markdown report generation.
7. Add prompt patch proposal generation.
8. Add direct `Agent` adapter.
9. Add regression replay and patch application.
10. Add SQLite indexing and report/list/replay CLI commands.

This order gets a useful harness working quickly without forcing a major agent
refactor up front. The direct agent adapter can come after the API path proves
that the simulated-user/evaluator/prompt-editor loop is valuable.
