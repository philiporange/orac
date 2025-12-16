"""
Centralized argument parsing with validation for Orac CLI.

Handles the two-phase argument parsing required for dynamic parameters
from YAML specs, with proper validation of unknown flags.
"""

import argparse
import json
import sys
from typing import Any, Callable, Optional

from .errors import show_unknown_flag_error, show_missing_required_arg_error


def convert_cli_value(value: str, param_type: str, param_name: str) -> Any:
    """
    Convert CLI string values to appropriate Python types.

    Args:
        value: The string value from CLI
        param_type: The expected type (string, int, float, bool, list, etc.)
        param_name: Name of the parameter (for error messages)

    Returns:
        Converted value of appropriate type

    Raises:
        SystemExit: If conversion fails
    """
    if param_type in ("bool", "boolean"):
        return value.lower() in ("true", "1", "yes", "on", "y")

    elif param_type in ("int", "integer"):
        try:
            return int(value)
        except ValueError:
            print(
                f"Error: Parameter '{param_name}' expects an integer, got '{value}'",
                file=sys.stderr,
            )
            sys.exit(1)

    elif param_type in ("float", "number"):
        try:
            return float(value)
        except ValueError:
            print(
                f"Error: Parameter '{param_name}' expects a number, got '{value}'",
                file=sys.stderr,
            )
            sys.exit(1)

    elif param_type in ("list", "array"):
        return [item.strip() for item in value.split(",") if item.strip()]

    else:
        return value


def safe_json_parse(label: str, json_string: str) -> Any:
    """
    Safely parse JSON string with proper error handling.

    Args:
        label: Description of what's being parsed (for error message)
        json_string: The JSON string to parse

    Returns:
        Parsed JSON value

    Raises:
        SystemExit: If JSON is invalid
    """
    try:
        return json.loads(json_string)
    except Exception as e:
        print(f"Error: {label} is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)


def format_help_text(param: dict) -> str:
    """
    Generate enhanced help text for a parameter.

    Args:
        param: Parameter definition dict with 'name', 'type', 'description', 'default', 'required'

    Returns:
        Formatted help string
    """
    help_parts = []

    if "description" in param:
        help_parts.append(param["description"])
    else:
        help_parts.append(f"Parameter '{param['name']}'")

    param_type = param.get("type", "string")
    help_parts.append(f"(type: {param_type})")

    has_default = "default" in param
    is_required = param.get("required", not has_default)

    if is_required and not has_default:
        help_parts.append("REQUIRED")
    elif has_default:
        default_val = param["default"]
        if param_type in ("list", "array") and isinstance(default_val, list):
            default_str = (
                ",".join(map(str, default_val)) if default_val else "empty list"
            )
        else:
            default_str = str(default_val)
        help_parts.append(f"default: {default_str}")

    return " ".join(help_parts)


def add_parameter_to_parser(parser: argparse.ArgumentParser, param: dict) -> None:
    """
    Add a parameter from a YAML spec as a CLI argument.

    Args:
        parser: The argparse parser to add to
        param: Parameter definition dict
    """
    name = param["name"]
    arg_name = f"--{name.replace('_', '-')}"
    param_type = param.get("type", "string")

    has_default = "default" in param
    is_required = param.get("required", not has_default)
    cli_required = is_required and not has_default

    help_text = format_help_text(param)

    if param_type in ("bool", "boolean"):
        if has_default:
            default_bool = bool(param["default"])
            const_value = "false" if default_bool else "true"
            parser.add_argument(
                arg_name,
                dest=name,
                nargs="?",
                const=const_value,
                default=None,
                help=f"{help_text}",
            )
        else:
            parser.add_argument(
                arg_name,
                dest=name,
                help=f"{help_text} (true/false)",
                required=cli_required,
            )
    else:
        parser.add_argument(
            arg_name, dest=name, help=help_text, required=cli_required, default=None
        )


class DynamicArgumentParser:
    """
    Handles dynamic argument parsing from YAML specs with validation.

    This parser handles the two-phase parsing needed when CLI arguments
    are defined dynamically in YAML files (like prompt parameters).
    """

    def __init__(
        self,
        resource_type: str,
        resource_name: Optional[str] = None,
        global_flags: Optional[list[str]] = None,
    ):
        """
        Initialize the parser.

        Args:
            resource_type: Type of resource (prompt, flow, skill, etc.)
            resource_name: Name of specific resource (for error messages)
            global_flags: List of global flag names that should be ignored
        """
        self.resource_type = resource_type
        self.resource_name = resource_name
        self.global_flags = set(global_flags or [])

        # Standard global flags that are always allowed
        self.global_flags.update(
            [
                "verbose",
                "v",
                "quiet",
                "q",
                "provider",
                "api-key",
                "model-name",
                "output",
                "o",
                "help",
                "h",
                # Resource-level directory flags
                "prompts-dir",
                "flows-dir",
                "skills-dir",
                "agents-dir",
                "teams-dir",
            ]
        )

    def build_parser_from_params(
        self, params: list[dict], additional_args: Optional[Callable] = None
    ) -> argparse.ArgumentParser:
        """
        Build an argparse parser from parameter definitions.

        Args:
            params: List of parameter definition dicts
            additional_args: Optional function to add extra args to parser

        Returns:
            Configured ArgumentParser
        """
        parser = argparse.ArgumentParser(add_help=False)

        # Add resource-specific execution args if provided
        if additional_args:
            additional_args(parser)

        # Add dynamic parameters from spec
        for param in params:
            add_parameter_to_parser(parser, param)

        return parser

    def parse_with_validation(
        self,
        parser: argparse.ArgumentParser,
        args: list[str],
        known_params: list[str],
    ) -> argparse.Namespace:
        """
        Parse arguments and validate for unknown flags.

        Args:
            parser: The configured parser
            args: List of command-line arguments
            known_params: List of parameter names defined in the spec

        Returns:
            Parsed arguments namespace

        Raises:
            SystemExit: If unknown flags are found
        """
        parsed, unknown = parser.parse_known_args(args)

        # Check for unknown flags (those starting with -)
        unknown_flags = [u for u in unknown if u.startswith("-")]

        if unknown_flags:
            # Filter out global flags that are handled at the top level
            truly_unknown = []
            for flag in unknown_flags:
                flag_name = flag.lstrip("-")
                if flag_name not in self.global_flags:
                    truly_unknown.append(flag)

            if truly_unknown:
                # Get the first unknown flag for the error
                flag = truly_unknown[0]

                # Build list of valid flags from params + common flags
                valid_flags = list(known_params)
                valid_flags.extend(
                    [
                        "json-output",
                        "output",
                        "file",
                        "file-url",
                        "generation-config",
                        "response-schema",
                        "conversation-id",
                        "reset-conversation",
                        "no-save",
                        "base-url",
                        "dry-run",
                    ]
                )

                # Normalize for comparison (convert underscores to dashes)
                valid_flags_normalized = [f.replace("_", "-") for f in valid_flags]

                show_command = None
                if self.resource_name:
                    show_command = f"orac {self.resource_type} show {self.resource_name}"

                show_unknown_flag_error(flag, valid_flags_normalized, show_command)

        return parsed

    def collect_param_values(
        self, parsed_args: argparse.Namespace, params: list[dict]
    ) -> dict[str, Any]:
        """
        Collect and convert parameter values from parsed args.

        Args:
            parsed_args: Parsed argparse namespace
            params: Parameter definitions from spec

        Returns:
            Dict of parameter name -> converted value
        """
        values = {}

        for param in params:
            name = param["name"]
            cli_value = getattr(parsed_args, name, None)
            param_type = param.get("type", "string")

            if cli_value is not None:
                values[name] = convert_cli_value(cli_value, param_type, name)
            elif "default" in param:
                values[name] = param["default"]

        return values

    def check_required_params(
        self, values: dict[str, Any], params: list[dict]
    ) -> None:
        """
        Check that all required parameters have values.

        Args:
            values: Collected parameter values
            params: Parameter definitions from spec

        Raises:
            SystemExit: If required parameter is missing
        """
        for param in params:
            name = param["name"]
            has_default = "default" in param
            is_required = param.get("required", not has_default)

            if is_required and name not in values:
                show_missing_required_arg_error(
                    name.replace("_", "-"),
                    self.resource_type,
                    self.resource_name,
                )


def get_param_names(params: list[dict]) -> list[str]:
    """
    Extract parameter names from param definitions.

    Args:
        params: List of parameter definition dicts

    Returns:
        List of parameter names (with underscores converted to dashes)
    """
    return [p["name"].replace("_", "-") for p in params]
