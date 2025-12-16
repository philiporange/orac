"""
CLI commands for flows.

Handles execution, listing, showing, graphing, and testing of flow YAML files.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from orac.config import Config
from orac.flow import load_flow, Flow, list_flows, FlowValidationError, FlowExecutionError
from orac.cli_progress import create_cli_reporter

from .base import ResourceCommand, ListableMixin
from .parsing import (
    DynamicArgumentParser,
    get_param_names,
    convert_cli_value,
)


def add_flow_execution_args(parser: argparse.ArgumentParser) -> None:
    """Add execution-specific arguments for flows."""
    parser.add_argument("--dry-run", action="store_true", help="Show execution plan without running")
    parser.add_argument("--json-output", action="store_true", help="Format final output as JSON")


class FlowCommand(ResourceCommand, ListableMixin):
    """CLI command handler for flows."""

    name = "flow"
    help_text = "Multi-step AI workflows"
    description = "Execute, discover, and explore flows"

    actions = {
        "run": {
            "help": "Execute a flow",
            "args": ["name"],
            "handler": "run",
            "add_args": add_flow_execution_args,
        },
        "list": {
            "help": "List all flows",
            "handler": "list",
        },
        "show": {
            "help": "Show flow structure",
            "args": ["name"],
            "handler": "show",
        },
        "graph": {
            "help": "Show dependency graph",
            "args": ["name"],
            "handler": "graph",
        },
        "test": {
            "help": "Dry-run validation",
            "args": ["name"],
            "handler": "test",
        },
    }

    examples = {
        "run": "orac flow run capital_recipe --country Italy",
        "list": "orac flow list",
        "show": "orac flow show research_assistant",
    }

    common_args = [
        (
            "--flows-dir",
            {
                "default": str(Config.get_flows_dir()),
                "help": "Directory where flow YAML files live",
            },
        ),
        (
            "--prompts-dir",
            {
                "default": str(Config.get_prompts_dir()),
                "help": "Directory where prompt YAML files live",
            },
        ),
    ]

    def get_resource_dir(self, args: argparse.Namespace) -> Path:
        """Get the flows directory."""
        return Path(args.flows_dir)

    def load_spec_for_list(self, path: Path) -> dict:
        """Load spec for listing."""
        spec = load_flow(path)
        return {"description": spec.description or "No description"}

    def handle_run(self, args: argparse.Namespace, remaining: list[str]) -> None:
        """Execute a flow with dynamic parameter loading."""
        flows_dir = self.get_resource_dir(args)
        path = self.check_resource_exists(args.name, flows_dir)

        try:
            spec = load_flow(path)

            # Build params list from flow inputs
            params_spec = [
                {
                    "name": inp.name,
                    "type": inp.type,
                    "description": inp.description,
                    "required": inp.required,
                    "default": inp.default,
                }
                for inp in spec.inputs
            ]

            dyn_parser = DynamicArgumentParser(
                resource_type="flow",
                resource_name=args.name,
            )

            parser = dyn_parser.build_parser_from_params(
                params_spec,
                additional_args=add_flow_execution_args,
            )

            param_names = get_param_names(params_spec)
            flow_args = dyn_parser.parse_with_validation(parser, remaining, param_names)

            progress_callback = None
            if not args.quiet:
                reporter = create_cli_reporter(verbose=args.verbose, quiet=args.quiet)
                progress_callback = reporter.report

            engine = Flow(spec, prompts_dir=args.prompts_dir, progress_callback=progress_callback)

            inputs = {}
            for flow_input in spec.inputs:
                cli_value = getattr(flow_args, flow_input.name, None)
                if cli_value is not None:
                    converted_value = convert_cli_value(cli_value, flow_input.type, flow_input.name)
                    inputs[flow_input.name] = converted_value
                elif flow_input.default is not None:
                    inputs[flow_input.name] = flow_input.default

            logger.debug(f"Flow inputs: {inputs}")

            results = engine.execute(inputs, dry_run=getattr(flow_args, "dry_run", False))

            if getattr(flow_args, "dry_run", False):
                print("DRY RUN - Flow execution plan:")
                print(f"Execution order: {' -> '.join(engine.execution_order)}")
                return

            if args.output:
                try:
                    with open(args.output, "w", encoding="utf-8") as f:
                        if getattr(flow_args, "json_output", False):
                            json.dump(results, f, indent=2)
                        else:
                            for name, value in results.items():
                                f.write(f"{name}: {value}\n")
                    logger.info(f"Flow output written to file: {args.output}")
                except IOError as e:
                    logger.error(f"Error writing to output file '{args.output}': {e}")
                    print(f"Error writing to output file '{args.output}': {e}", file=sys.stderr)
                    sys.exit(1)
            else:
                if getattr(flow_args, "json_output", False):
                    print(json.dumps(results, indent=2))
                else:
                    for name, value in results.items():
                        print(f"{name}: {value}")

            logger.info("Flow completed successfully")

        except (FlowValidationError, FlowExecutionError) as e:
            logger.error(f"Flow error: {e}")
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            logger.error(f"Unexpected error running flow: {e}")
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    def handle_show(self, args: argparse.Namespace, remaining: list[str]) -> None:
        """Show detailed information about a flow."""
        flows_dir = self.get_resource_dir(args)
        path = self.check_resource_exists(args.name, flows_dir)

        try:
            spec = load_flow(path)
        except FlowValidationError as e:
            print(f"Error loading flow: {e}", file=sys.stderr)
            sys.exit(1)

        banner = f"Workflow: {spec.name}"
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
                print(f"  {out.name:20} <- {out.source}")
                if out.description:
                    print(f"    {out.description}")
                print()

        if spec.steps:
            print(f"Steps ({len(spec.steps)}):")
            for step_name, step in spec.steps.items():
                print(f"  {step_name:20} (prompt: {step.prompt_name})")
                if step.depends_on:
                    print(f"    Depends on: {', '.join(step.depends_on)}")
                print()

        example = [f"orac flow run {args.name}"]
        for inp in spec.inputs:
            if inp.required and inp.default is None:
                flag = f"--{inp.name.replace('_', '-')}"
                example.extend([flag, "'value'"])
        print("Example usage:\n ", " ".join(example))

    def handle_graph(self, args: argparse.Namespace, remaining: list[str]) -> None:
        """Show dependency graph for a flow."""
        flows_dir = self.get_resource_dir(args)
        path = self.check_resource_exists(args.name, flows_dir)

        try:
            spec = load_flow(path)
            engine = Flow(spec, prompts_dir=str(Config.get_prompts_dir()))

            print(f"\nDependency graph for flow '{args.name}':")
            print("-" * 50)
            print(f"Execution order: {' -> '.join(engine.execution_order)}")

            print("\nStep dependencies:")
            for step_name, step in spec.steps.items():
                if step.depends_on:
                    deps = ", ".join(step.depends_on)
                    print(f"  {step_name} depends on: {deps}")
                else:
                    print(f"  {step_name} (no dependencies)")

        except (FlowValidationError, FlowExecutionError) as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    def handle_test(self, args: argparse.Namespace, remaining: list[str]) -> None:
        """Test/validate a flow with dry run."""
        flows_dir = self.get_resource_dir(args)
        path = self.check_resource_exists(args.name, flows_dir)

        try:
            spec = load_flow(path)
            engine = Flow(spec, prompts_dir=str(Config.get_prompts_dir()))

            print(f"\n✓ Flow '{args.name}' validation successful")
            print(f"Steps: {len(spec.steps)}")
            print(f"Inputs: {len(spec.inputs)}")
            print(f"Outputs: {len(spec.outputs)}")
            print(f"Execution order: {' -> '.join(engine.execution_order)}")

            test_inputs = {}
            for inp in spec.inputs:
                if inp.default is not None:
                    test_inputs[inp.name] = inp.default

            print("\nDry run test passed - flow structure is valid")

        except (FlowValidationError, FlowExecutionError) as e:
            print(f"✗ Flow test failed: {e}", file=sys.stderr)
            sys.exit(1)


# Module-level instance for backwards compatibility
_flow_command = FlowCommand()


def add_flow_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Add flow resource parser (for backwards compatibility)."""
    return _flow_command.setup_parser(subparsers)


def handle_flow_commands(args: argparse.Namespace, remaining: list[str]) -> None:
    """Handle flow resource commands (for backwards compatibility)."""
    _flow_command.handle(args, remaining)
