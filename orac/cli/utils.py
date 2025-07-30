#!/usr/bin/env python3

import argparse
import os
import sys
import yaml
import json
from loguru import logger
from pathlib import Path

from orac.config import Config


def load_prompt_spec(prompts_dir: str, prompt_name: str) -> dict:
    """
    Return the YAML mapping for *prompt_name*.

    *prompt_name* can be either:
      • a bare name (searched in *prompts_dir*), or
      • a direct path to a *.yaml / *.yml* file.
    """
    if prompt_name.endswith((".yaml", ".yml")) and os.path.isfile(prompt_name):
        path = prompt_name
    else:
        path = os.path.join(prompts_dir, f"{prompt_name}.yaml")

    if not os.path.isfile(path):
        logger.error(f"Prompt '{prompt_name}' not found.")
        print(f"Error: Prompt '{prompt_name}' not found.", file=sys.stderr)
        sys.exit(1)

    logger.debug(f"Loading prompt spec from: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        logger.error(f"Invalid YAML in '{path}'")
        print(f"Error: Invalid YAML in '{path}'", file=sys.stderr)
        sys.exit(1)

    logger.debug(f"Successfully loaded prompt spec with keys: {list(data.keys())}")
    return data


def convert_cli_value(value: str, param_type: str, param_name: str) -> any:
    """Convert CLI string values to appropriate types."""
    logger.debug(
        f"Converting CLI value '{value}' "
        f"to type '{param_type}' "
        f"for parameter '{param_name}'"
    )

    if param_type in ("bool", "boolean"):
        result = value.lower() in ("true", "1", "yes", "on", "y")
        logger.debug(f"Converted to boolean: {result}")
        return result
    elif param_type in ("int", "integer"):
        try:
            result = int(value)
            logger.debug(f"Converted to int: {result}")
            return result
        except ValueError:
            logger.error(f"Parameter '{param_name}' expects an integer, got '{value}'")
            print(
                f"Error: Parameter '{param_name}' expects an integer, got '{value}'",
                file=sys.stderr,
            )
            sys.exit(1)
    elif param_type in ("float", "number"):
        try:
            result = float(value)
            logger.debug(f"Converted to float: {result}")
            return result
        except ValueError:
            logger.error(f"Parameter '{param_name}' expects a number, got '{value}'")
            print(
                f"Error: Parameter '{param_name}' expects a number, got '{value}'",
                file=sys.stderr,
            )
            sys.exit(1)
    elif param_type in ("list", "array"):
        # Parse comma-separated values
        result = [item.strip() for item in value.split(",") if item.strip()]
        logger.debug(f"Converted to list: {result}")
        return result
    else:
        # Default to string
        logger.debug(f"Keeping as string: {value}")
        return value


def format_help_text(param: dict) -> str:
    """Generate enhanced help text for parameters."""
    help_parts = []

    # Base description
    if "description" in param:
        help_parts.append(param["description"])
    else:
        help_parts.append(f"Parameter '{param['name']}'")

    # Type information
    param_type = param.get("type", "string")
    help_parts.append(f"(type: {param_type})")

    # Required/Optional status
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


def add_parameter_argument(parser: argparse.ArgumentParser, param: dict):
    """Add a parameter as a CLI argument with appropriate type handling."""
    name = param["name"]
    arg_name = f"--{name.replace('_', '-')}"
    param_type = param.get("type", "string")

    has_default = "default" in param
    is_required = param.get("required", not has_default)

    help_text = format_help_text(param)

    # Determine if this should be required at CLI level
    cli_required = is_required and not has_default

    if param_type in ("bool", "boolean"):
        # For boolean parameters, use store_true/store_false or allow explicit values
        if has_default:
            default_bool = bool(param["default"])
            if default_bool:
                parser.add_argument(
                    arg_name,
                    dest=name,
                    nargs="?",
                    const="false",  # If flag provided without value, set to false
                    default=None,
                    help=(
                        f"{help_text}. "
                        f"Use --{name.replace('_', '-')} false to override default."
                    ),
                )
            else:
                parser.add_argument(
                    arg_name,
                    dest=name,
                    nargs="?",
                    const="true",  # If flag provided without value, set to true
                    default=None,
                    help=(
                        f"{help_text}. "
                        f"Use --{name.replace('_', '-')} true to override default."
                    ),
                )
        else:
            parser.add_argument(
                arg_name,
                dest=name,
                help=help_text + " (true/false)",
                required=cli_required,
            )
    else:
        parser.add_argument(
            arg_name, dest=name, help=help_text, required=cli_required, default=None
        )


def add_flow_input_argument(parser: argparse.ArgumentParser, flow_input):
    """Add a flow input as a CLI argument."""
    name = flow_input.name
    arg_name = f"--{name.replace('_', '-')}"
    
    help_parts = []
    if flow_input.description:
        help_parts.append(flow_input.description)
    
    help_parts.append(f"(type: {flow_input.type})")
    
    if flow_input.required and flow_input.default is None:
        help_parts.append("REQUIRED")
    elif flow_input.default is not None:
        help_parts.append(f"default: {flow_input.default}")
    
    help_text = " ".join(help_parts)
    
    cli_required = flow_input.required and flow_input.default is None
    
    parser.add_argument(
        arg_name,
        dest=name,
        help=help_text,
        required=cli_required,
        default=None
    )


def safe_json_parse(label: str, json_string: str):
    """Safely parse JSON string with proper error handling."""
    try:
        return json.loads(json_string)
    except Exception as e:
        logger.error(f"{label} JSON parse error: {e}")
        print(f"Error: {label} is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)