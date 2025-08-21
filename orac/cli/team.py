"""CLI commands for teams."""

import argparse
import sys
from pathlib import Path

from orac.config import Config, Provider
from orac.team import Team, load_team_spec
from orac.registry import ToolRegistry
from orac.providers import ProviderRegistry
from .utils import add_parameter_argument, convert_cli_value


def add_team_parser(subparsers):
    """Add team resource parser."""
    team_parser = subparsers.add_parser(
        'team',
        help='Teams of collaborative agents',
        description='Execute and manage agent teams'
    )

    team_parser.add_argument(
        '--teams-dir',
        default="orac/teams",
        help='Directory where team YAML files live'
    )

    team_parser.add_argument(
        '--agents-dir', 
        default="orac/agents",
        help='Directory where agent YAML files live'
    )

    team_subparsers = team_parser.add_subparsers(
        dest='action',
        help='Available actions'
    )

    # run action
    run_parser = team_subparsers.add_parser('run', help='Execute a team')
    run_parser.add_argument('name', help='Name of the team to run')

    # list action
    list_parser = team_subparsers.add_parser('list', help='List all teams')

    # show action
    show_parser = team_subparsers.add_parser('show', help='Show team details')
    show_parser.add_argument('name', help='Name of the team to show')

    return team_parser


def handle_team_commands(args, remaining):
    """Handle team resource commands."""
    if args.action == 'run':
        execute_team(args, remaining)
    elif args.action == 'list':
        list_teams_command(args.teams_dir)
    elif args.action == 'show':
        show_team_info(args.teams_dir, args.name)
    else:
        print(f"Unknown team action: {args.action}", file=sys.stderr)
        sys.exit(1)


def execute_team(args, remaining_args):
    """Execute a team with dynamic parameter loading."""
    team_path = Path(args.teams_dir) / f"{args.name}.yaml"

    if not team_path.exists():
        print(f"Error: Team '{args.name}' not found at {team_path}", file=sys.stderr)
        sys.exit(1)

    try:
        spec = load_team_spec(team_path)

        # Create parser for team inputs
        team_parser = argparse.ArgumentParser(add_help=False)
        for param in spec.inputs:
            add_parameter_argument(team_parser, param)

        # Parse remaining args
        team_args, _ = team_parser.parse_known_args(remaining_args)

        # Collect input values
        input_values = {}
        for param in spec.inputs:
            name = param["name"]
            cli_value = getattr(team_args, name, None)
            param_type = param.get("type", "string")

            if cli_value is not None:
                converted_value = convert_cli_value(cli_value, param_type, name)
                input_values[name] = converted_value
            elif param.get("default") is not None:
                input_values[name] = param["default"]
            elif param.get("required", True):
                print(f"Error: Missing required argument --{name}", file=sys.stderr)
                sys.exit(1)

        # Setup provider and run team
        provider = Provider(args.provider or "openrouter")
        registry = ToolRegistry()
        provider_registry = ProviderRegistry()
        team = Team(
            team_spec=spec,
            registry=registry,
            provider_registry=provider_registry,
            provider=provider,
            agents_dir=args.agents_dir
        )

        result = team.run(**input_values)
        print(f"\n--- TEAM RESULT ---\n{result}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def list_teams_command(teams_dir: str):
    """List available teams."""
    teams_path = Path(teams_dir)
    if not teams_path.exists():
        print(f"Teams directory not found: {teams_dir}")
        return

    yaml_files = list(teams_path.glob('*.yaml'))
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


def show_team_info(teams_dir: str, team_name: str):
    """Show detailed information about a team."""
    team_path = Path(teams_dir) / f"{team_name}.yaml"

    if not team_path.exists():
        print(f"Team '{team_name}' not found at {team_path}", file=sys.stderr)
        sys.exit(1)

    try:
        spec = load_team_spec(team_path)
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
            status = "REQUIRED" if inp.get('required', True) else "OPTIONAL"
            name = inp['name']
            param_type = inp.get('type', 'string')
            print(f"  --{name:20} ({param_type}) [{status}]")
            if inp.get('description'):
                print(f"    {inp['description']}")

    # Example usage
    example = [f"orac team run {team_name}"]
    for inp in spec.inputs:
        if inp.get('required', True) and inp.get('default') is None:
            flag = f"--{inp['name'].replace('_', '-')}"
            example.extend([flag, "'value'"])
    print(f"\nExample usage:\n  {' '.join(example)}")