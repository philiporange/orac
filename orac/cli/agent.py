"""
CLI commands for agents.

Handles execution, listing, and showing of agent YAML files.
"""

import argparse
import sys
from pathlib import Path
from typing import Any

from loguru import logger

from orac.config import Config, Provider
from orac.agent import Agent, load_agent_spec
from orac.registry import ToolRegistry
from orac.providers import ProviderRegistry

from .base import ResourceCommand, ListableMixin
from .parsing import (
    DynamicArgumentParser,
    get_param_names,
    convert_cli_value,
)


class AgentCommand(ResourceCommand, ListableMixin):
    """CLI command handler for agents."""

    name = "agent"
    help_text = "Autonomous agents for complex tasks"
    description = "Execute and manage autonomous agents"

    actions = {
        "run": {
            "help": "Execute an agent",
            "args": ["name"],
            "handler": "run",
        },
        "list": {
            "help": "List all agents",
            "handler": "list",
        },
        "show": {
            "help": "Show agent details",
            "args": ["name"],
            "handler": "show",
        },
    }

    examples = {
        "run": "orac agent run geo_cuisine_agent --country Thailand",
        "list": "orac agent list",
        "show": "orac agent show research_agent",
    }

    common_args = [
        (
            "--agents-dir",
            {
                "default": str(Config.get_agents_dir()),
                "help": "Directory where agent YAML files live",
            },
        ),
    ]

    def get_resource_dir(self, args: argparse.Namespace) -> Path:
        """Get the agents directory."""
        return Path(args.agents_dir)

    def load_spec_for_list(self, path: Path) -> dict:
        """Load spec for listing."""
        spec = load_agent_spec(path)
        return {"description": spec.description or "No description"}

    def handle_run(self, args: argparse.Namespace, remaining: list[str]) -> None:
        """Execute an agent with dynamic parameter loading."""
        agents_dir = self.get_resource_dir(args)
        path = self.check_resource_exists(args.name, agents_dir)

        spec = load_agent_spec(path)

        # Build params list from agent inputs
        params_spec = spec.inputs  # Already list of dicts

        dyn_parser = DynamicArgumentParser(
            resource_type="agent",
            resource_name=args.name,
        )

        parser = dyn_parser.build_parser_from_params(params_spec)

        param_names = get_param_names(params_spec)
        agent_args = dyn_parser.parse_with_validation(parser, remaining, param_names)

        # Collect input values
        input_values = dyn_parser.collect_param_values(agent_args, params_spec)
        dyn_parser.check_required_params(input_values, params_spec)

        # Setup Provider
        provider_str = args.provider or spec.provider or "openrouter"
        provider = Provider(provider_str)
        api_key = args.api_key

        try:
            registry = ToolRegistry()
            provider_registry = ProviderRegistry()

            provider_registry.add_provider(
                provider,
                api_key=api_key,
                allow_env=True,
                interactive=True,
            )

            engine = Agent(spec, registry, provider_registry, provider)

            final_result = engine.run(**input_values)

            if args.output:
                with open(args.output, "w", encoding="utf-8") as f:
                    f.write(final_result)
                print(f"\nFinal agent output written to {args.output}")
            else:
                print(f"\n--- FINAL AGENT RESULT ---\n{final_result}")

        except Exception as e:
            logger.error(f"Error running agent: {e}")
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    def handle_show(self, args: argparse.Namespace, remaining: list[str]) -> None:
        """Show detailed information about an agent."""
        agents_dir = self.get_resource_dir(args)
        path = self.check_resource_exists(args.name, agents_dir)

        try:
            spec = load_agent_spec(path)
        except Exception as e:
            print(f"Error loading agent: {e}", file=sys.stderr)
            sys.exit(1)

        banner = f"Agent: {spec.name}"
        print(f"\n{banner}\n{'=' * len(banner)}")

        if spec.description:
            print(f"Description: {spec.description}\n")

        if spec.inputs:
            print(f"Inputs ({len(spec.inputs)}):")
            for inp in spec.inputs:
                status = "REQUIRED" if inp.get("required", True) else "OPTIONAL"
                name = inp["name"]
                param_type = inp.get("type", "string")
                print(f"  --{name.replace('_', '-'):20} ({param_type}) [{status}]")
                if inp.get("description"):
                    print(f"    {inp['description']}")
                if inp.get("default") is not None:
                    print(f"    Default: {inp['default']}")
                print()
        else:
            print("No inputs defined.")

        if hasattr(spec, "tools") and spec.tools:
            print(f"Tools ({len(spec.tools)}):")
            for tool in spec.tools:
                print(f"  {tool}")
            print()

        if hasattr(spec, "model_name") and spec.model_name:
            print(f"Model: {spec.model_name}")

        if hasattr(spec, "max_iterations") and spec.max_iterations:
            print(f"Max iterations: {spec.max_iterations}")

        example = [f"orac agent run {args.name}"]
        for inp in spec.inputs:
            if inp.get("required", True) and inp.get("default") is None:
                flag = f"--{inp['name'].replace('_', '-')}"
                example.extend([flag, "'value'"])
        print(f"\nExample usage:\n  {' '.join(example)}")


# Module-level instance for backwards compatibility
_agent_command = AgentCommand()


def add_agent_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Add agent resource parser (for backwards compatibility)."""
    return _agent_command.setup_parser(subparsers)


def handle_agent_commands(args: argparse.Namespace, remaining: list[str]) -> None:
    """Handle agent resource commands (for backwards compatibility)."""
    _agent_command.handle(args, remaining)
