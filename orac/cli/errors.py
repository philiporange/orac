"""
Unified error handling and help formatting for the Orac CLI.

Provides consistent error messages with fuzzy matching suggestions,
contextual help, and formatted output for all CLI commands.
"""

import sys
from difflib import get_close_matches
from typing import Optional


def error(
    message: str,
    suggestions: Optional[list[str]] = None,
    tip: Optional[str] = None,
    available: Optional[list[str]] = None,
    available_label: Optional[str] = None,
) -> None:
    """
    Print formatted error message and exit.

    Args:
        message: The main error message
        suggestions: Similar options (for "Did you mean:" section)
        tip: Additional help tip
        available: List of valid options to show
        available_label: Label for the available list (e.g., "Available prompts")
    """
    print(f"Error: {message}", file=sys.stderr)

    if suggestions:
        if len(suggestions) == 1:
            print(f"\nDid you mean: {suggestions[0]}", file=sys.stderr)
        else:
            print(f"\nDid you mean one of: {', '.join(suggestions)}", file=sys.stderr)

    if available and available_label:
        print(f"\n{available_label}: {', '.join(available)}", file=sys.stderr)

    if tip:
        print(f"\nTip: {tip}", file=sys.stderr)

    sys.exit(1)


def suggest_similar(
    input_str: str, valid_options: list[str], cutoff: float = 0.6, n: int = 3
) -> list[str]:
    """
    Find similar strings using fuzzy matching.

    Args:
        input_str: The user's input that may have a typo
        valid_options: List of valid options to match against
        cutoff: Minimum similarity ratio (0.0 to 1.0)
        n: Maximum number of suggestions to return

    Returns:
        List of similar strings, sorted by similarity
    """
    return get_close_matches(input_str, valid_options, n=n, cutoff=cutoff)


def show_missing_action_help(
    resource: str,
    actions: dict[str, str],
    examples: Optional[dict[str, str]] = None,
) -> None:
    """
    Show helpful error when no action is specified.

    Args:
        resource: The resource name (e.g., "prompt")
        actions: Dict mapping action names to help text
        examples: Dict mapping action names to example commands
    """
    print(f"Error: Please specify an action for '{resource}'.\n", file=sys.stderr)

    print("Available actions:", file=sys.stderr)
    max_action_len = max(len(a) for a in actions.keys())
    for action, help_text in actions.items():
        print(f"  {action:<{max_action_len + 2}} {help_text}", file=sys.stderr)

    if examples:
        print("\nExamples:", file=sys.stderr)
        for action, example in examples.items():
            print(f"  {example}", file=sys.stderr)

    print(f"\nFor help: orac {resource} --help", file=sys.stderr)
    sys.exit(1)


def show_unknown_action_error(
    resource: str, action: str, valid_actions: list[str]
) -> None:
    """
    Show error for unknown action with suggestions.

    Args:
        resource: The resource name (e.g., "prompt")
        action: The unknown action the user tried
        valid_actions: List of valid action names
    """
    suggestions = suggest_similar(action, valid_actions)
    error(
        f"Unknown action '{action}' for '{resource}'.",
        suggestions=suggestions,
        available=valid_actions,
        available_label="Available actions",
    )


def show_unknown_resource_error(resource: str, valid_resources: list[str]) -> None:
    """
    Show error for unknown resource with suggestions.

    Args:
        resource: The unknown resource the user tried
        valid_resources: List of valid resource names
    """
    suggestions = suggest_similar(resource, valid_resources)
    error(
        f"Unknown resource '{resource}'.",
        suggestions=suggestions,
        available=valid_resources,
        available_label="Available resources",
    )


def show_resource_not_found_error(
    resource_type: str,
    name: str,
    available: list[str],
    list_command: str,
) -> None:
    """
    Show error when a specific resource (prompt, flow, etc.) is not found.

    Args:
        resource_type: Type of resource (e.g., "Prompt", "Flow")
        name: The name that wasn't found
        available: List of available resources
        list_command: Command to list all resources (e.g., "orac prompt list")
    """
    suggestions = suggest_similar(name, available)

    # Limit shown available items to keep output manageable
    shown_available = available[:10]
    if len(available) > 10:
        shown_available.append(f"... and {len(available) - 10} more")

    error(
        f"{resource_type} '{name}' not found.",
        suggestions=suggestions,
        available=shown_available,
        available_label=f"Available {resource_type.lower()}s",
        tip=f"Run '{list_command}' for full list with descriptions.",
    )


def show_unknown_flag_error(
    flag: str, valid_flags: list[str], show_command: Optional[str] = None
) -> None:
    """
    Show error for unknown CLI flag with suggestions.

    Args:
        flag: The unknown flag (e.g., "--counrty")
        valid_flags: List of valid flag names (without --)
        show_command: Optional command to show valid options
    """
    # Normalize flag for matching (remove leading dashes)
    flag_name = flag.lstrip("-")
    suggestions = suggest_similar(flag_name, valid_flags)

    # Add -- prefix back to suggestions for display
    if suggestions:
        suggestions = [f"--{s}" for s in suggestions]

    tip = f"Run '{show_command}' to see available options." if show_command else None

    error(
        f"Unknown option '{flag}'.",
        suggestions=suggestions,
        tip=tip,
    )


def show_missing_required_arg_error(
    arg_name: str,
    resource_type: str,
    resource_name: Optional[str] = None,
) -> None:
    """
    Show error for missing required argument.

    Args:
        arg_name: Name of the missing argument
        resource_type: Type of resource (e.g., "prompt", "flow")
        resource_name: Name of the specific resource if known
    """
    msg = f"Missing required argument '--{arg_name}'."

    tip = None
    if resource_name:
        tip = f"Run 'orac {resource_type} show {resource_name}' to see all options."

    error(msg, tip=tip)


def format_action_table(actions: dict[str, str], indent: int = 2) -> str:
    """
    Format actions as an aligned table.

    Args:
        actions: Dict mapping action names to descriptions
        indent: Number of spaces for indentation

    Returns:
        Formatted table string
    """
    if not actions:
        return ""

    max_len = max(len(a) for a in actions.keys())
    lines = []
    for action, desc in actions.items():
        lines.append(f"{' ' * indent}{action:<{max_len + 2}} {desc}")
    return "\n".join(lines)


def format_items_list(items: list[str], max_items: int = 10) -> str:
    """
    Format a list of items with truncation.

    Args:
        items: List of item names
        max_items: Maximum items to show before truncating

    Returns:
        Comma-separated string with truncation indicator if needed
    """
    if len(items) <= max_items:
        return ", ".join(items)

    shown = items[:max_items]
    remaining = len(items) - max_items
    return f"{', '.join(shown)}, ... and {remaining} more"
