"""
Code execution skill using autonomous coding agents.

Runs a coding task using Claude Code (default) or other supported coding agents.
The agent operates in autonomous mode to complete the task without requiring
user interaction.

Supported agents:
- claude_code: Claude Code CLI (default) - supports custom API endpoints
- codex: OpenAI Codex CLI
- aider: Aider coding assistant
- goose: Block Goose CLI
"""

import subprocess
import tempfile
import os
from typing import Dict, Any
from pathlib import Path


def execute(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a coding task using an autonomous coding agent.

    Args:
        inputs: Dictionary containing:
            - prompt (str): The coding task to execute
            - working_directory (str, optional): Directory to work in
            - agent (str, optional): Coding agent to use (default: claude_code)
            - model (str, optional): Model to use (default: opus)
            - system (str, optional): System prompt override
            - system_addendum (str, optional): Text to append to system prompt
            - api_endpoint (str, optional): Custom API endpoint URL
            - api_key (str, optional): API key for the endpoint

    Returns:
        Dictionary containing:
            - result (str): Output from the coding agent
            - working_directory (str): The directory used
    """
    prompt = inputs['prompt']
    agent = inputs.get('agent', 'claude_code')
    model = inputs.get('model', 'opus')
    system = inputs.get('system')
    system_addendum = inputs.get('system_addendum')
    api_endpoint = inputs.get('api_endpoint')
    api_key = inputs.get('api_key')
    working_directory = inputs.get('working_directory')

    # Create temp directory if none provided
    if not working_directory:
        working_directory = tempfile.mkdtemp(prefix='orac_code_')
    else:
        working_directory = os.path.expanduser(working_directory)
        Path(working_directory).mkdir(parents=True, exist_ok=True)

    agent_runners = {
        'claude_code': _run_claude_code,
        'codex': _run_codex,
        'aider': _run_aider,
        'goose': _run_goose,
    }

    runner = agent_runners.get(agent)
    if not runner:
        raise ValueError(f"Unsupported agent: {agent}. Supported: {list(agent_runners.keys())}")

    result = runner(
        prompt=prompt,
        working_directory=working_directory,
        model=model,
        system=system,
        system_addendum=system_addendum,
        api_endpoint=api_endpoint,
        api_key=api_key,
    )

    return {
        'result': result,
        'working_directory': working_directory
    }


def _run_claude_code(prompt: str, working_directory: str, model: str,
                     system: str | None, system_addendum: str | None,
                     api_endpoint: str | None, api_key: str | None) -> str:
    """
    Execute using Claude Code CLI.

    Supports custom API endpoints via environment variables, allowing use with
    alternative providers like z.ai (GLM4.6) or other OpenAI-compatible APIs.
    """
    cmd = [
        'claude',
        '--print',
        '--dangerously-skip-permissions',
        '--model', model,
    ]

    if system:
        cmd.extend(['--system-prompt', system])

    if system_addendum:
        cmd.extend(['--append-system-prompt', system_addendum])

    cmd.append(prompt)

    # Build environment with API overrides
    env = os.environ.copy()
    if api_endpoint:
        env['ANTHROPIC_BASE_URL'] = api_endpoint
    if api_key:
        env['ANTHROPIC_API_KEY'] = api_key

    result = subprocess.run(
        cmd,
        cwd=working_directory,
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
    )

    if result.returncode != 0:
        error_msg = result.stderr or result.stdout or "Unknown error"
        raise RuntimeError(f"Claude Code failed: {error_msg}")

    return result.stdout.strip()


def _run_codex(prompt: str, working_directory: str, model: str,
               system: str | None, system_addendum: str | None,
               api_endpoint: str | None, api_key: str | None) -> str:
    """Execute using OpenAI Codex CLI."""
    cmd = [
        'codex', 'exec',
        '--dangerously-bypass-approvals-and-sandbox',
        '--model', model,
    ]

    cmd.append(prompt)

    # Build environment with API overrides
    env = os.environ.copy()
    if api_endpoint:
        env['OPENAI_BASE_URL'] = api_endpoint
    if api_key:
        env['OPENAI_API_KEY'] = api_key

    result = subprocess.run(
        cmd,
        cwd=working_directory,
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
    )

    if result.returncode != 0:
        error_msg = result.stderr or result.stdout or "Unknown error"
        raise RuntimeError(f"Codex failed: {error_msg}")

    return result.stdout.strip()


def _run_aider(prompt: str, working_directory: str, model: str,
               system: str | None, system_addendum: str | None,
               api_endpoint: str | None, api_key: str | None) -> str:
    """Execute using Aider CLI."""
    cmd = [
        'aider',
        '--yes',
        '--no-git',
        '--message', prompt,
    ]

    # Map common model names to aider format
    model_map = {
        'opus': 'claude-3-opus-20240229',
        'sonnet': 'claude-3-5-sonnet-20241022',
        'gpt4': 'gpt-4',
        'gpt4o': 'gpt-4o',
        'o3': 'o3',
    }
    aider_model = model_map.get(model, model)
    cmd.extend(['--model', aider_model])

    # Aider doesn't have separate addendum - combine if both provided
    combined_system = None
    if system and system_addendum:
        combined_system = f"{system}\n\n{system_addendum}"
    elif system:
        combined_system = system
    elif system_addendum:
        combined_system = system_addendum

    if combined_system:
        cmd.extend(['--system-prompt', combined_system])

    # Build environment with API overrides
    env = os.environ.copy()
    if api_endpoint:
        env['OPENAI_API_BASE'] = api_endpoint
    if api_key:
        env['OPENAI_API_KEY'] = api_key

    result = subprocess.run(
        cmd,
        cwd=working_directory,
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
    )

    if result.returncode != 0:
        error_msg = result.stderr or result.stdout or "Unknown error"
        raise RuntimeError(f"Aider failed: {error_msg}")

    return result.stdout.strip()


def _run_goose(prompt: str, working_directory: str, model: str,
               system: str | None, system_addendum: str | None,
               api_endpoint: str | None, api_key: str | None) -> str:
    """Execute using Block Goose CLI."""
    cmd = [
        'goose', 'run',
        '--text', prompt,
    ]

    # Build environment with API overrides
    env = os.environ.copy()
    if api_endpoint:
        env['OPENAI_BASE_URL'] = api_endpoint
    if api_key:
        env['OPENAI_API_KEY'] = api_key

    result = subprocess.run(
        cmd,
        cwd=working_directory,
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
    )

    if result.returncode != 0:
        error_msg = result.stderr or result.stdout or "Unknown error"
        raise RuntimeError(f"Goose failed: {error_msg}")

    return result.stdout.strip()
