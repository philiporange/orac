"""
CLI commands for prompts.

Handles execution, listing, showing, and validation of prompt YAML files.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from orac.config import Config
from orac.prompt import Prompt
from orac.cli_progress import create_cli_reporter

from .base import ResourceCommand, ListableMixin, ValidatableMixin
from .errors import show_resource_not_found_error
from .parsing import (
    DynamicArgumentParser,
    add_parameter_to_parser,
    get_param_names,
    safe_json_parse,
    convert_cli_value,
)


def add_prompt_execution_args(parser: argparse.ArgumentParser) -> None:
    """Add execution-specific arguments for prompts."""
    parser.add_argument("--base-url", help="Custom base URL")
    parser.add_argument("--generation-config", help="JSON string for generation_config")

    parser.add_argument(
        "--file",
        action="append",
        dest="files",
        help="Add file(s) to the request (can be used multiple times)",
    )
    parser.add_argument(
        "--file-url",
        action="append",
        dest="file_urls",
        help="Download remote file(s) via URL (can be used multiple times)",
    )

    parser.add_argument(
        "--json-output",
        action="store_true",
        help="Format response as JSON",
    )
    parser.add_argument(
        "--response-schema",
        metavar="FILE",
        help="Validate against JSON schema",
    )

    parser.add_argument("--conversation-id", help="Specify conversation ID")
    parser.add_argument(
        "--reset-conversation",
        action="store_true",
        help="Reset conversation before starting",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save messages to conversation history",
    )


class PromptCommand(ResourceCommand, ListableMixin, ValidatableMixin):
    """CLI command handler for prompts."""

    name = "prompt"
    help_text = "Single AI interactions"
    description = "Execute, discover, and explore prompts"

    actions = {
        "run": {
            "help": "Execute a prompt",
            "args": ["name"],
            "handler": "run",
            "add_args": add_prompt_execution_args,
        },
        "list": {
            "help": "List all available prompts",
            "handler": "list",
        },
        "show": {
            "help": "Show prompt details & parameters",
            "args": ["name"],
            "handler": "show",
        },
        "validate": {
            "help": "Validate prompt YAML",
            "args": ["name"],
            "handler": "validate",
        },
    }

    examples = {
        "run": "orac prompt run capital --country France",
        "list": "orac prompt list",
        "show": "orac prompt show capital",
    }

    common_args = [
        (
            "--prompts-dir",
            {
                "default": str(Config.get_prompts_dir()),
                "help": "Directory where prompt YAML files live",
            },
        ),
    ]

    def get_resource_dir(self, args: argparse.Namespace) -> Path:
        """Get the prompts directory."""
        return Path(args.prompts_dir)

    def load_spec(self, path: Path) -> dict:
        """Load a prompt spec from a YAML file."""
        import yaml

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError(f"Invalid YAML in '{path}'")

        return data

    def load_spec_for_list(self, path: Path) -> dict:
        """Load spec for listing."""
        return self.load_spec(path)

    def load_spec_for_validation(self, path: Path) -> dict:
        """Load spec for validation."""
        return self.load_spec(path)

    def additional_validation(self, spec: dict, name: str) -> None:
        """Perform additional prompt-specific validation."""
        if "prompt" not in spec:
            print("⚠ Warning: No 'prompt' field found")

        if "parameters" in spec:
            params = spec["parameters"]
            if not isinstance(params, list):
                print("⚠ Warning: 'parameters' should be a list")
            else:
                for i, param in enumerate(params):
                    if not isinstance(param, dict):
                        print(f"⚠ Warning: Parameter {i} should be a dictionary")
                    elif "name" not in param:
                        print(f"⚠ Warning: Parameter {i} missing 'name' field")

    def handle_run(self, args: argparse.Namespace, remaining: list[str]) -> None:
        """Execute a prompt with dynamic parameter loading."""
        prompts_dir = self.get_resource_dir(args)
        path = self.check_resource_exists(args.name, prompts_dir)
        spec = self.load_spec(path)

        params_spec = spec.get("parameters", [])

        # Set up dynamic argument parser
        dyn_parser = DynamicArgumentParser(
            resource_type="prompt",
            resource_name=args.name,
        )

        parser = dyn_parser.build_parser_from_params(
            params_spec,
            additional_args=add_prompt_execution_args,
        )

        # Parse with validation
        param_names = get_param_names(params_spec)
        prompt_args = dyn_parser.parse_with_validation(parser, remaining, param_names)

        # Parse JSON overrides
        gen_config = (
            safe_json_parse("generation_config", prompt_args.generation_config)
            if getattr(prompt_args, "generation_config", None)
            else {}
        )

        # Structured output injection
        if getattr(prompt_args, "json_output", False):
            gen_config = gen_config or {}
            gen_config["response_mime_type"] = "application/json"

        if getattr(prompt_args, "response_schema", None):
            try:
                with open(prompt_args.response_schema, "r", encoding="utf-8") as f:
                    schema_json = json.load(f)
            except Exception as e:
                logger.error(f"Failed to read schema file '{prompt_args.response_schema}': {e}")
                print(f"Error reading schema file: {e}", file=sys.stderr)
                sys.exit(1)
            gen_config = gen_config or {}
            gen_config["response_schema"] = schema_json

        # Collect and convert parameter values
        param_values = dyn_parser.collect_param_values(prompt_args, params_spec)

        logger.debug(f"Final parameter values: {param_values}")

        # Create Prompt instance and execute
        try:
            logger.debug("Creating Prompt instance")

            progress_callback = None
            if not args.quiet:
                reporter = create_cli_reporter(verbose=args.verbose, quiet=args.quiet)
                progress_callback = reporter.report

            wrapper = Prompt(
                prompt_name=args.name,
                prompts_dir=str(prompts_dir),
                model_name=args.model_name,
                generation_config=gen_config or None,
                verbose=args.verbose,
                files=getattr(args, "files", None),
                file_urls=getattr(args, "file_urls", None),
                provider=args.provider,
                conversation_id=getattr(args, "conversation_id", None),
                auto_save=not getattr(args, "no_save", False),
                progress_callback=progress_callback,
            )

            if getattr(args, "reset_conversation", False):
                wrapper.reset_conversation()
                logger.info("Reset conversation history")

            logger.debug("Calling completion method")
            result = wrapper.completion(**param_values)

            if args.output:
                try:
                    with open(args.output, "w", encoding="utf-8") as f:
                        f.write(result)
                    logger.info(f"Output written to file: {args.output}")
                except IOError as e:
                    logger.error(f"Error writing to output file '{args.output}': {e}")
                    print(f"Error writing to output file '{args.output}': {e}", file=sys.stderr)
                    sys.exit(1)
            else:
                print(result)

            logger.info("Successfully completed prompt execution")

        except Exception as e:
            logger.error(f"Error running prompt: {e}")
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    def handle_show(self, args: argparse.Namespace, remaining: list[str]) -> None:
        """Show prompt details and parameters."""
        prompts_dir = self.get_resource_dir(args)
        path = self.check_resource_exists(args.name, prompts_dir)
        spec = self.load_spec(path)
        params = spec.get("parameters", [])

        banner = f"Prompt: {args.name}"
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
        example = [f"orac prompt run {args.name}"]
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


# Module-level instance for backwards compatibility
_prompt_command = PromptCommand()


def add_prompt_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Add prompt resource parser (for backwards compatibility)."""
    return _prompt_command.setup_parser(subparsers)


def handle_prompt_commands(args: argparse.Namespace, remaining: list[str]) -> None:
    """Handle prompt resource commands (for backwards compatibility)."""
    _prompt_command.handle(args, remaining)
