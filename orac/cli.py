#!/usr/bin/env python3

import argparse
import os
import sys
import yaml
import json
from loguru import logger
from dotenv import load_dotenv, find_dotenv
from pathlib import Path

from orac.logger import configure_console_logging
from orac.config import Config
from orac.llm import LLMWrapper

# --------------------------------------------------------------------------- #
# Load environment variables (.env)                                           #
# --------------------------------------------------------------------------- #
# 1. Current working directory and parents
load_dotenv(find_dotenv(usecwd=True), override=False)
# 2. Project root
load_dotenv(Config.PROJECT_ROOT / ".env", override=False)
# 3. User’s home directory
load_dotenv(Path.home() / ".env", override=False)


# --------------------------------------------------------------------------- #
# Helper functions                                                            #
# --------------------------------------------------------------------------- #
def load_prompt_spec(prompts_dir: str, prompt_name: str) -> dict:
    path = os.path.join(prompts_dir, f"{prompt_name}.yaml")
    if not os.path.isfile(path):
        logger.error(f"Prompt '{prompt_name}' not found in '{prompts_dir}'")
        print(
            f"Error: Prompt '{prompt_name}' not found in '{prompts_dir}'",
            file=sys.stderr,
        )
        sys.exit(1)

    logger.debug(f"Loading prompt spec from: {path}")
    with open(path, "r") as f:
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


def show_prompt_info(prompts_dir: str, prompt_name: str) -> None:
    """
    Display parameters and defaults for *prompt_name* without touching the LLM
    layer, so it works even when no provider/API key is configured.
    """
    spec = load_prompt_spec(prompts_dir, prompt_name)
    params = spec.get("parameters", [])

    banner = f"Prompt: {prompt_name}"
    print(f"\n{banner}\n{'=' * len(banner)}")

    if params:
        print(f"\nParameters ({len(params)}):")
        for p in params:
            name = p["name"]
            ptype = p.get("type", "string")
            has_default = "default" in p
            required = p.get("required", not has_default)
            status = "REQUIRED" if required else "OPTIONAL"
            print(f"  --{name.replace('_', '-'):20} ({ptype}) [{status}]")
            if desc := p.get("description"):
                print(f"    {desc}")
            if has_default:
                print(f"    Default: {p['default']}")
            print()
    else:
        print("\nNo parameters defined.")

    # Compact example
    example = [f"python -m orac {prompt_name}"]
    for p in params:
        if p.get("required", "default" not in p):
            flag = f"--{p['name'].replace('_', '-')}"
            sample = {
                "bool": "true",
                "boolean": "true",
                "int": "42",
                "integer": "42",
                "float": "3.14",
                "number": "3.14",
                "list": "'a,b,c'",
                "array": "'a,b,c'",
            }.get(p.get("type", "string"), "'value'")
            example.extend([flag, sample])
    print("Example usage:\n ", " ".join(example))


def main():
    # First pass: get prompt name and check for info request
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument(
        "prompt", help="Name of the prompt (yaml file without .yaml)"
    )
    pre_parser.add_argument(
        "--prompts-dir",
        default=Config.DEFAULT_PROMPTS_DIR,
        help="Directory where prompt YAML files live",
    )
    pre_parser.add_argument(
        "--info",
        action="store_true",
        help="Show detailed information about the prompt and its parameters",
    )
    pre_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging output"
    )
    pre_args, remaining_argv = pre_parser.parse_known_args()

    # Configure logging based on verbose setting
    configure_console_logging(verbose=pre_args.verbose)

    logger.debug(f"CLI started with prompt: {pre_args.prompt}")
    logger.debug(f"Verbose mode: {pre_args.verbose}")
    logger.debug(f"Prompts directory: {pre_args.prompts_dir}")

    # If --info requested, show info and exit
    if pre_args.info:
        logger.debug("Info mode requested")
        show_prompt_info(pre_args.prompts_dir, pre_args.prompt)
        return

    spec = load_prompt_spec(pre_args.prompts_dir, pre_args.prompt)
    params_spec = spec.get("parameters", [])

    parser = argparse.ArgumentParser(
        prog=os.path.basename(sys.argv[0]),
        description=spec.get("description", f"Run prompt '{pre_args.prompt}'"),
        parents=[pre_parser],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Global overrides
    parser.add_argument("--model-name", help="Override model_name for the LLM")
    parser.add_argument("--api-key", help="Override API key for LLM")
    parser.add_argument(
        "--provider",
        choices=["openai", "google", "anthropic", "azure", "openrouter", "custom"],
        help="Select LLM provider (openai|google|anthropic|azure|openrouter|custom)",
    )
    parser.add_argument(
        "--base-url", help="Custom base URL for CUSTOM provider or to override default"
    )
    parser.add_argument("--generation-config", help="JSON string for generation_config")
    parser.add_argument(
        "--file",
        action="append",
        dest="files",
        help="Add file(s) to the request (can be used multiple times)",
    )
    # Remote file URLs
    parser.add_argument(
        "--file-url",
        action="append",
        dest="file_urls",
        help="Download remote file(s) via URL (can be used multiple times)",
    )
    parser.add_argument(
        "--output", "-o", help="Write output to specified file instead of stdout"
    )
    # Structured JSON output
    parser.add_argument(
        "--json-output",
        action="store_true",
        help="Request strict JSON output (sets response_mime_type=application/json)",
    )
    parser.add_argument(
        "--response-schema",
        metavar="FILE",
        help="Path to JSON schema file for response_schema (OpenAPI style)",
    )

    # Add parameters from the prompt spec with enhanced type support
    for param in params_spec:
        add_parameter_argument(parser, param)

    # Add usage examples to help
    if params_spec:
        examples = ["\nExamples:"]
        examples.append(
            f"  python cli.py {pre_args.prompt} --info  # Show parameter details"
        )

        # Basic example
        required_params = [
            p for p in params_spec if p.get("required", "default" not in p)
        ]
        if required_params:
            basic_args = []
            for param in required_params[:2]:  # Show first 2 required params
                arg_name = f"--{param['name'].replace('_', '-')}"
                basic_args.append(f"{arg_name} example")
            examples.append(f"  python cli.py {pre_args.prompt} {' '.join(basic_args)}")

        parser.epilog = "\n".join(examples)

    args = parser.parse_args()

    logger.debug(f"Parsed arguments: {vars(args)}")

    # Parse JSON overrides
    def _safe_json(label: str, s: str):
        try:
            return json.loads(s)
        except Exception as e:
            logger.error(f"{label} JSON parse error: {e}")
            print(f"Error: {label} is not valid JSON: {e}", file=sys.stderr)
            sys.exit(1)

    gen_config = (
        _safe_json("generation_config", args.generation_config)
        if args.generation_config
        else {}
    )

    # Structured output injection
    if args.json_output:
        gen_config = gen_config or {}
        gen_config["response_mime_type"] = "application/json"

    if args.response_schema:
        try:
            with open(args.response_schema, "r", encoding="utf-8") as f:
                schema_json = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read schema file '{args.response_schema}': {e}")
            print(f"Error reading schema file: {e}", file=sys.stderr)
            sys.exit(1)
        gen_config = gen_config or {}
        gen_config["response_schema"] = schema_json

    # Collect and convert parameter values
    param_values = {}
    for param in params_spec:
        name = param["name"]
        cli_value = getattr(args, name)
        param_type = param.get("type", "string")

        if cli_value is not None:
            # Convert CLI string to appropriate type
            converted_value = convert_cli_value(cli_value, param_type, name)
            param_values[name] = converted_value

    logger.debug(f"Final parameter values: {param_values}")

    # Instantiate wrapper and call
    try:
        logger.debug("Creating LLMWrapper instance")
        wrapper = LLMWrapper(
            prompt_name=args.prompt,
            prompts_dir=args.prompts_dir,
            model_name=args.model_name,
            api_key=args.api_key,
            generation_config=gen_config or None,
            verbose=args.verbose,
            files=args.files,
            file_urls=args.file_urls,
            provider=args.provider,
            base_url=args.base_url,
        )

        logger.debug("Calling completion method")
        result = wrapper.completion(**param_values)

        # Output result to file or stdout
        if args.output:
            try:
                with open(args.output, "w", encoding="utf-8") as f:
                    f.write(result)
                logger.info(f"Output written to file: {args.output}")
            except IOError as e:
                logger.error(f"Error writing to output file '{args.output}': {e}")
                print(
                    f"Error writing to output file '{args.output}': {e}",
                    file=sys.stderr,
                )
                sys.exit(1)
        else:
            # Output only the result (no additional formatting)
            print(result)

        logger.info("Successfully completed prompt execution")

    except Exception as e:
        logger.error(f"Error running prompt: {e}")
        # Always show critical errors to user, regardless of verbose mode
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
