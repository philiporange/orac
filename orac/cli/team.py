"""
CLI commands for teams.

Handles execution, listing, and showing of team YAML files.
"""

import argparse
import sys
from pathlib import Path
from typing import Any

from orac.config import Config, Provider
from orac.team import Team, load_team_spec
from orac.registry import ToolRegistry

from .base import ResourceCommand, ListableMixin
from .parsing import (
    DynamicArgumentParser,
    get_param_names,
    convert_cli_value,
)


class TeamCommand(ResourceCommand, ListableMixin):
    """CLI command handler for teams."""

    name = "team"
    help_text = "Teams of collaborative agents"
    description = "Execute and manage agent teams"

    actions = {
        "run": {
            "help": "Execute a team",
            "args": ["name"],
            "handler": "run",
        },
        "list": {
            "help": "List all teams",
            "handler": "list",
        },
        "show": {
            "help": "Show team details",
            "args": ["name"],
            "handler": "show",
        },
    }

    examples = {
        "run": "orac team run research_team --topic 'AI ethics'",
        "list": "orac team list",
        "show": "orac team show research_team",
    }

    common_args = [
        (
            "--teams-dir",
            {
                "default": "orac/teams",
                "help": "Directory where team YAML files live",
            },
        ),
        (
            "--agents-dir",
            {
                "default": "orac/agents",
                "help": "Directory where agent YAML files live",
            },
        ),
    ]

    def get_resource_dir(self, args: argparse.Namespace) -> Path:
        """Get the teams directory."""
        return Path(args.teams_dir)

    def load_spec_for_list(self, path: Path) -> dict:
        """Load spec for listing."""
        spec = load_team_spec(path)
        return {"description": spec.description or "No description"}

    def handle_list(self, args: argparse.Namespace, remaining: list[str]) -> None:
        """List available teams with custom formatting."""
        teams_dir = self.get_resource_dir(args)

        if not teams_dir.exists():
            print(f"Teams directory not found: {teams_dir}")
            return

        yaml_files = list(teams_dir.glob("*.yaml"))
        if not yaml_files:
            print(f"No teams found in {teams_dir}")
            return

        print(f"\nAvailable teams ({len(yaml_files)} total):")
        print("-" * 60)
        print(f"{'Name':20} {'Leader':15} {'Agents':8} {'Description':17}")
        print("-" * 60)

        for yaml_file in sorted(yaml_files):
            name = yaml_file.stem
            try:
                spec = load_team_spec(yaml_file)
                desc = (spec.description[:14] + "...") if len(spec.description) > 17 else spec.description
                agent_count = len(spec.agents)
                print(f"{name:20} {spec.leader:15} {agent_count:8} {desc:17}")
            except Exception:
                print(f"{name:20} {'(Error loading)':40}")

    def handle_run(self, args: argparse.Namespace, remaining: list[str]) -> None:
        """Execute a team with dynamic parameter loading."""
        teams_dir = self.get_resource_dir(args)
        path = self.check_resource_exists(args.name, teams_dir)

        try:
            spec = load_team_spec(path)

            # Build params list from team inputs
            params_spec = spec.inputs  # Already list of dicts

            dyn_parser = DynamicArgumentParser(
                resource_type="team",
                resource_name=args.name,
            )

            parser = dyn_parser.build_parser_from_params(params_spec)

            param_names = get_param_names(params_spec)
            team_args = dyn_parser.parse_with_validation(parser, remaining, param_names)

            # Collect input values
            input_values = dyn_parser.collect_param_values(team_args, params_spec)
            dyn_parser.check_required_params(input_values, params_spec)

            registry = ToolRegistry()
            team = Team(
                team_spec=spec,
                registry=registry,
                agents_dir=args.agents_dir,
            )

            result = team.run(**input_values)
            print(f"\n--- TEAM RESULT ---\n{result}")

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    def handle_show(self, args: argparse.Namespace, remaining: list[str]) -> None:
        """Show detailed information about a team."""
        teams_dir = self.get_resource_dir(args)
        path = self.check_resource_exists(args.name, teams_dir)

        try:
            spec = load_team_spec(path)
        except Exception as e:
            print(f"Error loading team: {e}", file=sys.stderr)
            sys.exit(1)

        print(f"\n{'='*50}")
        print(f"Team: {spec.name}")
        print(f"{'='*50}")

        if spec.description:
            print(f"Description: {spec.description}\n")

        print(f"Leader: {spec.leader}")

        if spec.agents:
            print(f"\nTeam Members ({len(spec.agents)}):")
            for agent in spec.agents:
                print(f"  - {agent}")

        if spec.constitution:
            print(f"\nTeam Constitution:")
            print(spec.constitution)

        if spec.inputs:
            print(f"\nInputs ({len(spec.inputs)}):")
            for inp in spec.inputs:
                status = "REQUIRED" if inp.get("required", True) else "OPTIONAL"
                name = inp["name"]
                param_type = inp.get("type", "string")
                print(f"  --{name:20} ({param_type}) [{status}]")
                if inp.get("description"):
                    print(f"    {inp['description']}")

        example = [f"orac team run {args.name}"]
        for inp in spec.inputs:
            if inp.get("required", True) and inp.get("default") is None:
                flag = f"--{inp['name'].replace('_', '-')}"
                example.extend([flag, "'value'"])
        print(f"\nExample usage:\n  {' '.join(example)}")


# Module-level instance for backwards compatibility
_team_command = TeamCommand()


def add_team_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Add team resource parser (for backwards compatibility)."""
    return _team_command.setup_parser(subparsers)


def handle_team_commands(args: argparse.Namespace, remaining: list[str]) -> None:
    """Handle team resource commands (for backwards compatibility)."""
    _team_command.handle(args, remaining)


# Keep for backwards compatibility
def list_teams_command(teams_dir: str) -> None:
    """List available teams."""
    class FakeArgs:
        pass
    fake_args = FakeArgs()
    fake_args.teams_dir = teams_dir
    _team_command.handle_list(fake_args, [])
