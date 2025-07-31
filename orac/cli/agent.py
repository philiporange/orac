#!/usr/bin/env python3

import argparse
import sys
import os
from loguru import logger
from pathlib import Path

from orac.config import Config, Provider
from orac.agent import Agent, load_agent_spec
from orac.registry import ToolRegistry
from .utils import add_parameter_argument, convert_cli_value


def add_agent_parser(subparsers):
    """Add agent resource parser."""
    agent_parser = subparsers.add_parser(
        'agent',
        help='Autonomous agents for complex tasks',
        description='Execute and manage autonomous agents'
    )
    agent_parser.add_argument(
        '--agents-dir',
        default=Config.DEFAULT_AGENTS_DIR,
        help='Directory where agent YAML files live'
    )
    
    agent_subparsers = agent_parser.add_subparsers(
        dest='action',
        help='Available actions',
        metavar='<action>'
    )
    
    run_parser = agent_subparsers.add_parser('run', help='Execute an agent')
    run_parser.add_argument('name', help='Name of the agent to run')
    # We will add dynamic args later
    
    # list action
    list_parser = agent_subparsers.add_parser('list', help='List all agents')
    
    # show action
    show_parser = agent_subparsers.add_parser('show', help='Show agent details')
    show_parser.add_argument('name', help='Name of the agent to show')

    return agent_parser


def handle_agent_commands(args, remaining):
    """Handle agent resource commands."""
    if args.action == 'run':
        execute_agent(args, remaining)
    elif args.action == 'list':
        list_agents_command(args.agents_dir)
    elif args.action == 'show':
        show_agent_info(args.agents_dir, args.name)
    else:
        print(f"Unknown agent action: {args.action}", file=sys.stderr)
        sys.exit(1)


def execute_agent(args, remaining_args):
    """Execute an agent with dynamic parameter loading."""
    agent_path = Path(args.agents_dir) / f"{args.name}.yaml"
    if not agent_path.exists():
        print(f"Error: Agent '{args.name}' not found at {agent_path}", file=sys.stderr)
        sys.exit(1)
        
    spec = load_agent_spec(agent_path)
    
    # Dynamically add arguments for the agent's inputs
    agent_parser = argparse.ArgumentParser(add_help=False)
    for param in spec.inputs:
        add_parameter_argument(agent_parser, param)
        
    # Parse remaining args to get parameter values - ignore unknown args from global scope
    agent_args, _ = agent_parser.parse_known_args(remaining_args)
    
    # Collect input values
    input_values = {}
    for param in spec.inputs:
        name = param["name"]
        cli_value = getattr(agent_args, name, None)
        param_type = param.get("type", "string")

        if cli_value is not None:
            converted_value = convert_cli_value(cli_value, param_type, name)
            input_values[name] = converted_value
        elif param.get('required'):
             print(f"Error: Missing required argument --{name}", file=sys.stderr)
             sys.exit(1)

    # Setup Provider
    provider_str = args.provider or os.getenv("ORAC_LLM_PROVIDER")
    if not provider_str:
        print("Error: LLM provider not specified. Use --provider or set ORAC_LLM_PROVIDER.", file=sys.stderr)
        sys.exit(1)
    provider = Provider(provider_str)
    api_key = args.api_key # Can be None, will be picked up from env by client

    try:
        # Initialize components
        registry = ToolRegistry()
        engine = Agent(spec, registry, provider, api_key)
        
        # Run the agent
        final_result = engine.run(**input_values)
        
        # Handle output
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


def list_agents_command(agents_dir: str):
    """List available agents."""
    agents_path = Path(agents_dir)
    if not agents_path.exists():
        print(f"Agents directory not found: {agents_dir}")
        return
    
    yaml_files = list(agents_path.glob('*.yaml')) + list(agents_path.glob('*.yml'))
    
    if not yaml_files:
        print(f"No agents found in {agents_dir}")
        return
    
    print(f"\nAvailable agents ({len(yaml_files)} total):")
    print("-" * 80)
    print(f"{'Name':20} {'Description':60}")
    print("-" * 80)
    
    for yaml_file in sorted(yaml_files):
        name = yaml_file.stem
        try:
            spec = load_agent_spec(yaml_file)
            desc = spec.description or 'No description available'
            desc = desc[:57] + "..." if len(desc) > 60 else desc
            print(f"{name:20} {desc:60}")
        except:
            print(f"{name:20} {'(Error loading agent)':60}")


def show_agent_info(agents_dir: str, agent_name: str):
    """Show detailed information about an agent."""
    agent_path = Path(agents_dir) / f"{agent_name}.yaml"
    
    if not agent_path.exists():
        print(f"Agent '{agent_name}' not found at {agent_path}", file=sys.stderr)
        sys.exit(1)
    
    try:
        spec = load_agent_spec(agent_path)
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
            status = "REQUIRED" if inp.get('required', True) else "OPTIONAL"
            name = inp['name']
            param_type = inp.get('type', 'string')
            print(f"  --{name.replace('_', '-'):20} ({param_type}) [{status}]")
            if inp.get('description'):
                print(f"    {inp['description']}")
            if inp.get('default') is not None:
                print(f"    Default: {inp['default']}")
            print()
    else:
        print("No inputs defined.")
    
    if hasattr(spec, 'tools') and spec.tools:
        print(f"Tools ({len(spec.tools)}):")
        for tool in spec.tools:
            print(f"  {tool}")
        print()
    
    if hasattr(spec, 'model_name') and spec.model_name:
        print(f"Model: {spec.model_name}")
    
    if hasattr(spec, 'max_iterations') and spec.max_iterations:
        print(f"Max iterations: {spec.max_iterations}")
    
    # Example usage
    example = [f"orac agent run {agent_name}"]
    for inp in spec.inputs:
        if inp.get('required', True) and inp.get('default') is None:
            flag = f"--{inp['name'].replace('_', '-')}"
            example.extend([flag, f"'{inp.get('type', 'string') == 'string' and 'value' or 'value'}'"])
    print(f"\nExample usage:\n  {' '.join(example)}")