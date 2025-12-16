"""
CLI commands for skills.

Handles execution, listing, showing, and validation of skill YAML files.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from orac.config import Config
from orac.skill import load_skill, Skill, list_skills, SkillValidationError, SkillExecutionError
from orac.cli_progress import create_cli_reporter

from .base import ResourceCommand, ListableMixin, ValidatableMixin
from .parsing import (
    DynamicArgumentParser,
    get_param_names,
    convert_cli_value,
)


def add_skill_execution_args(parser: argparse.ArgumentParser) -> None:
    """Add execution-specific arguments for skills."""
    parser.add_argument("--json-output", action="store_true", help="Format output as JSON")


class SkillCommand(ResourceCommand, ListableMixin, ValidatableMixin):
    """CLI command handler for skills."""

    name = "skill"
    help_text = "Runnable skills"
    description = "Execute and manage skills"

    actions = {
        "run": {
            "help": "Execute a skill",
            "args": ["name"],
            "handler": "run",
            "add_args": add_skill_execution_args,
        },
        "list": {
            "help": "List all available skills",
            "handler": "list",
        },
        "show": {
            "help": "Show skill details",
            "args": ["name"],
            "handler": "show",
        },
        "validate": {
            "help": "Validate skill definition",
            "args": ["name"],
            "handler": "validate",
        },
    }

    examples = {
        "run": "orac skill run calculator --expression '2 + 2'",
        "list": "orac skill list",
        "show": "orac skill show calculator",
    }

    common_args = [
        (
            "--skills-dir",
            {
                "default": str(Config.get_skills_dir()),
                "help": "Directory where skill YAML files live",
            },
        ),
    ]

    def get_resource_dir(self, args: argparse.Namespace) -> Path:
        """Get the skills directory."""
        return Path(args.skills_dir)

    def load_spec_for_list(self, path: Path) -> dict:
        """Load spec for listing."""
        spec = load_skill(path)
        return {"description": spec.description or "No description"}

    def load_spec_for_validation(self, path: Path) -> Any:
        """Load spec for validation."""
        return load_skill(path)

    def additional_validation(self, spec: Any, name: str) -> None:
        """Perform additional skill-specific validation."""
        if not hasattr(spec, "name"):
            print("⚠ Warning: No 'name' field found")
        if not hasattr(spec, "description"):
            print("⚠ Warning: No 'description' field found")
        if not hasattr(spec, "inputs"):
            print("⚠ Warning: No 'inputs' field found")
        if not hasattr(spec, "outputs"):
            print("⚠ Warning: No 'outputs' field found")

    def handle_run(self, args: argparse.Namespace, remaining: list[str]) -> None:
        """Execute a skill with dynamic parameter loading."""
        skills_dir = self.get_resource_dir(args)
        path = self.check_resource_exists(args.name, skills_dir)

        try:
            spec = load_skill(path)

            # Build params list from skill inputs
            params_spec = [inp.__dict__ for inp in spec.inputs]

            dyn_parser = DynamicArgumentParser(
                resource_type="skill",
                resource_name=args.name,
            )

            parser = dyn_parser.build_parser_from_params(
                params_spec,
                additional_args=add_skill_execution_args,
            )

            param_names = get_param_names(params_spec)
            skill_args = dyn_parser.parse_with_validation(parser, remaining, param_names)

            progress_callback = None
            if not args.quiet:
                reporter = create_cli_reporter(verbose=args.verbose, quiet=args.quiet)
                progress_callback = reporter.report

            engine = Skill(spec, skills_dir=str(skills_dir), progress_callback=progress_callback)

            inputs = {}
            for skill_input in spec.inputs:
                cli_value = getattr(skill_args, skill_input.name, None)
                if cli_value is not None:
                    converted_value = convert_cli_value(cli_value, skill_input.type, skill_input.name)
                    inputs[skill_input.name] = converted_value
                elif skill_input.default is not None:
                    inputs[skill_input.name] = skill_input.default

            logger.debug(f"Skill inputs: {inputs}")

            results = engine.execute(inputs)

            if args.output:
                try:
                    with open(args.output, "w", encoding="utf-8") as f:
                        if getattr(skill_args, "json_output", False):
                            json.dump(results, f, indent=2)
                        else:
                            print(results, file=f)
                    logger.info(f"Skill output written to file: {args.output}")
                except IOError as e:
                    logger.error(f"Error writing to output file '{args.output}': {e}")
                    print(f"Error writing to output file '{args.output}': {e}", file=sys.stderr)
                    sys.exit(1)
            else:
                if getattr(skill_args, "json_output", False):
                    print(json.dumps(results, indent=2))
                else:
                    print(results)

            logger.info("Skill completed successfully")

        except (SkillValidationError, SkillExecutionError) as e:
            logger.error(f"Skill error: {e}")
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            logger.error(f"Unexpected error running skill: {e}")
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    def handle_show(self, args: argparse.Namespace, remaining: list[str]) -> None:
        """Show detailed information about a skill."""
        skills_dir = self.get_resource_dir(args)
        path = self.check_resource_exists(args.name, skills_dir)

        try:
            spec = load_skill(path)
        except SkillValidationError as e:
            print(f"Error loading skill: {e}", file=sys.stderr)
            sys.exit(1)

        banner = f"Skill: {spec.name}"
        print(f"\n{banner}\n{'=' * len(banner)}")

        if spec.description:
            print(f"Description: {spec.description}\n")

        if spec.inputs:
            print(f"Inputs ({len(spec.inputs)}):")
            for inp in spec.inputs:
                status = "REQUIRED" if inp.required else "OPTIONAL"
                print(f"  --{inp.name.replace('_', '-'):20} ({inp.type}) [{status}]")
                if inp.description:
                    print(f"    {inp.description}")
                if inp.default is not None:
                    print(f"    Default: {inp.default}")
                print()
        else:
            print("No inputs defined.")

        if spec.outputs:
            print(f"Outputs ({len(spec.outputs)}):")
            for out in spec.outputs:
                print(f"  {out.name:20} ({out.type})")
                if out.description:
                    print(f"    {out.description}")
                print()

        example = [f"orac skill run {args.name}"]
        for inp in spec.inputs:
            if inp.required and inp.default is None:
                flag = f"--{inp.name.replace('_', '-')}"
                example.extend([flag, "'value'"])
        print("Example usage:\n ", " ".join(example))


# Module-level instance for backwards compatibility
_skill_command = SkillCommand()


def add_skill_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Add skill resource parser (for backwards compatibility)."""
    return _skill_command.setup_parser(subparsers)


def handle_skill_commands(args: argparse.Namespace, remaining: list[str]) -> None:
    """Handle skill resource commands (for backwards compatibility)."""
    _skill_command.handle(args, remaining)
