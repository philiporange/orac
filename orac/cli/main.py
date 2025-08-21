#!/usr/bin/env python3

import argparse
import os
import sys
from dotenv import load_dotenv, find_dotenv
from pathlib import Path

from orac.logger import configure_console_logging
from orac.config import Config
from orac.auth import AuthManager
from orac.client import Client
import orac


# ──────────────────────────────────────────────────────────────────────────────
# Allow: python -m orac.cli /path/to/cli.py <prompt> ...
# Strip the redundant script-path so that <prompt> is argv[1].
# ──────────────────────────────────────────────────────────────────────────────
if len(sys.argv) > 1 and sys.argv[1].endswith("cli.py"):
    sys.argv.pop(1)

# --------------------------------------------------------------------------- #
# Load environment variables (.env)                                           #
# --------------------------------------------------------------------------- #
if not os.getenv("ORAC_DISABLE_DOTENV"):
    # 1. Current working directory and parents
    load_dotenv(find_dotenv(usecwd=True), override=False)
    # 2. Project root
    load_dotenv(Config.PROJECT_ROOT / ".env", override=False)
    # 3. User's home directory
    load_dotenv(Path.home() / ".env", override=False)


def needs_api_access(args):
    """Check if command needs API access."""
    # Commands that require LLM API access
    api_commands = {
        'prompt': ['run'],
        'flow': ['run'], 
        'agent': ['run'],
        'chat': ['send', 'interactive']
    }
    
    if args.resource in api_commands:
        return hasattr(args, 'action') and args.action in api_commands[args.resource]
    
    return False


def ensure_client_initialized(interactive: bool = True):
    """Ensure client is initialized with proper consent."""
    # Check if global client is already initialized
    if orac.is_initialized():
        return orac.get_client()
    
    auth_manager = AuthManager()
    
    # Check if we have any consented providers
    consented_providers = auth_manager.get_consented_providers()
    
    if not consented_providers:
        if interactive:
            print("🔐 Orac needs to access LLM providers to function.")
            print("This requires one-time consent to read API keys from environment variables.")
            print()
            return interactive_provider_setup()
        else:
            raise RuntimeError(
                "No consented providers found. Run 'orac auth init' first, "
                "or use 'orac auth login <provider> --allow-env' to grant consent."
            )
    
    # Use existing consent to initialize client
    client = Client(auth_manager)
    try:
        # Try to add providers that have consent
        for provider in consented_providers:
            try:
                client.add_provider(provider, from_config=True)
            except Exception as e:
                # Skip providers that can't be initialized (missing API keys, etc.)
                continue
        
        if client.is_initialized():
            # Set global client
            orac._global_client = client
            return client
        else:
            raise RuntimeError("No providers could be initialized with current consent")
            
    except Exception as e:
        if interactive:
            print(f"⚠️  Could not initialize with existing consent: {e}")
            print("Let's set up authentication interactively...")
            return interactive_provider_setup()
        else:
            raise


def interactive_provider_setup():
    """Interactive provider setup with consent."""
    print("Available providers:")
    print("  • openrouter (recommended - access to multiple models)")
    print("  • openai, google, anthropic, azure")
    print()
    
    # Recommend OpenRouter for multi-provider access
    default_provider = input("Which provider would you like to use? [openrouter]: ").strip().lower()
    if not default_provider:
        default_provider = "openrouter"
    
    try:
        from orac.config import Provider
        provider = Provider(default_provider)
    except ValueError:
        print(f"Unknown provider: {default_provider}")
        print("Falling back to openrouter...")
        provider = Provider.OPENROUTER
    
    try:
        # Initialize using orac.init() which handles consent
        client = orac.init(
            interactive=True,
            default_provider=provider
        )
        print(f"✅ Successfully initialized with {provider.value}")
        return client
        
    except Exception as e:
        print(f"❌ Failed to initialize: {e}")
        print("\n💡 You can also try:")
        print(f"   orac auth login {provider.value} --allow-env")
        sys.exit(1)


def main():
    """Main entry point using resource-action command structure."""
    
    # Main parser with resource-action structure
    parser = argparse.ArgumentParser(
        prog="orac",
        description="Orac - YAML-driven LLM framework with intuitive command structure",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Global flags (available on all commands per README)
    parser.add_argument(
        "--verbose", "-v", 
        action="store_true", 
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--quiet", "-q", 
        action="store_true", 
        help="Suppress progress output (only show errors)"
    )
    parser.add_argument(
        "--provider",
        choices=["openai", "google", "anthropic", "azure", "openrouter", "custom"],
        help="Override LLM provider"
    )
    parser.add_argument(
        "--api-key",
        help="Override API key"
    )
    parser.add_argument(
        "--model-name",
        help="Override model name"
    )
    parser.add_argument(
        "--output", "-o",
        help="Write output to file"
    )
    # Note: --help/-h is handled automatically by argparse
    
    # Create subparsers for resources
    subparsers = parser.add_subparsers(
        dest='resource', 
        help='Available resources',
        metavar='<resource>'
    )
    
    # Import resource modules and set up parsers
    from . import prompt, flow, skill, agent, chat, management
    
    # Add resource parsers
    prompt.add_prompt_parser(subparsers)
    flow.add_flow_parser(subparsers)
    skill.add_skill_parser(subparsers)
    agent.add_agent_parser(subparsers)
    chat.add_chat_parser(subparsers)
    management.add_config_parser(subparsers)
    management.add_auth_parser(subparsers)
    add_global_commands(subparsers)
    
    # Handle shortcuts and aliases
    args, remaining = handle_shortcuts_and_parse(parser)
    
    # Configure logging
    configure_console_logging(verbose=args.verbose)
    
    # Initialize client for commands that need API access
    if needs_api_access(args):
        try:
            client = ensure_client_initialized(interactive=True)
        except Exception as e:
            print(f"❌ Failed to initialize client: {e}", file=sys.stderr)
            sys.exit(1)
    
    # Route to appropriate handler
    if args.resource == 'prompt':
        prompt.handle_prompt_commands(args, remaining)
    elif args.resource == 'flow':
        flow.handle_flow_commands(args, remaining)
    elif args.resource == 'skill':
        skill.handle_skill_commands(args, remaining) 
    elif args.resource == 'agent':
        agent.handle_agent_commands(args, remaining)
    elif args.resource == 'chat':
        chat.handle_chat_commands(args, remaining)
    elif args.resource == 'config':  
        management.handle_config_commands(args, remaining)
    elif args.resource == 'auth':
        management.handle_auth_commands(args, remaining)
    elif args.resource in ['list', 'search']:
        handle_global_commands(args, remaining)
    else:
        # No resource specified, show help
        parser.print_help()
        sys.exit(1)


def add_global_commands(subparsers):
    """Add global discovery commands."""
    # list command
    list_parser = subparsers.add_parser(
        'list',
        help='List all prompts and flows',
        description='Discover everything available'
    )
    
    # search command
    search_parser = subparsers.add_parser(
        'search',
        help='Search by keyword',
        description='Search prompts and flows by keyword'
    )
    search_parser.add_argument('keyword', help='Search keyword')


def handle_shortcuts_and_parse(parser):
    """Handle shortcuts and aliases before parsing."""
    argv = sys.argv[1:]
    
    # Handle shortcuts - map old commands to new structure
    if len(argv) > 0:
        first_arg = argv[0]
        
        # Ultra-short aliases
        if first_arg == 'r' and len(argv) > 1:
            argv = ['prompt', 'run'] + argv[1:]
        elif first_arg == 'f' and len(argv) > 1:
            argv = ['flow', 'run'] + argv[1:]
        elif first_arg == 'c' and len(argv) > 1:
            argv = ['chat', 'send'] + argv[1:]
        elif first_arg == 'i':
            argv = ['chat', 'interactive'] + argv[1:]
        # Regular shortcuts
        elif first_arg == 'run' and len(argv) > 1:
            argv = ['prompt', 'run'] + argv[1:]
        elif first_arg == 'ask' and len(argv) > 1:
            argv = ['chat', 'send'] + argv[1:]
        elif first_arg == 'interactive':
            argv = ['chat', 'interactive'] + argv[1:]
        # Flow shortcut - 'orac flow research' -> 'orac flow run research'
        elif first_arg == 'flow' and len(argv) > 1 and argv[1] not in ['run', 'list', 'show', 'graph', 'test']:
            argv = ['flow', 'run'] + argv[1:]
        # Legacy single-prompt mode (no resource specified)
        elif first_arg not in ['prompt', 'flow', 'skill', 'agent', 'chat', 'config', 'auth', 'list', 'search'] and not first_arg.startswith('-'):
            # Assume it's a prompt name - convert to new format
            argv = ['prompt', 'run'] + argv
    
    # Parse with modified argv
    try:
        return parser.parse_known_args(argv)
    except SystemExit:
        # If parsing fails, show help
        parser.print_help()
        sys.exit(1)


def handle_global_commands(args, remaining):
    """Handle global discovery commands."""
    from .utils import load_prompt_spec
    from orac.flow import list_flows
    
    if args.resource == 'list':
        list_all_command()
    elif args.resource == 'search':
        search_command(args.keyword)
    else:
        print(f"Unknown global command: {args.resource}", file=sys.stderr)
        sys.exit(1)


def list_all_command():
    """List all prompts and flows."""
    print("All Available Resources:")
    print("=" * 50)
    
    # List prompts
    print("\nPROMPTS:")
    list_prompts_command(str(Config.get_prompts_dir()))
    
    # List flows
    print("\nFLOWS:")
    list_flows_command(str(Config.get_flows_dir()))


def list_prompts_command(prompts_dir: str):
    """List available prompts."""
    from .utils import load_prompt_spec
    
    prompts_path = Path(prompts_dir)
    if not prompts_path.exists():
        print(f"Prompts directory not found: {prompts_dir}")
        return
    
    yaml_files = list(prompts_path.glob('*.yaml')) + list(prompts_path.glob('*.yml'))
    
    if not yaml_files:
        print(f"No prompts found in {prompts_dir}")
        return
    
    print(f"\nAvailable prompts ({len(yaml_files)} total):")
    print("-" * 80)
    print(f"{'Name':20} {'Description':60}")
    print("-" * 80)
    
    for yaml_file in sorted(yaml_files):
        name = yaml_file.stem
        try:
            spec = load_prompt_spec(prompts_dir, name)
            desc = spec.get('description', 'No description available')
            desc = desc[:57] + "..." if len(desc) > 60 else desc
            print(f"{name:20} {desc:60}")
        except:
            print(f"{name:20} {'(Error loading prompt)':60}")


def list_flows_command(flows_dir: str):
    """List available flows."""
    from orac.flow import list_flows
    
    flows = list_flows(flows_dir)
    
    if not flows:
        print(f"No flows found in {flows_dir}")
        return
    
    print(f"\nAvailable flows ({len(flows)} total):")
    print("-" * 80)
    print(f"{'Name':20} {'Description':60}")
    print("-" * 80)
    
    for flow in flows:
        name = flow['name']
        desc = flow['description'][:57] + "..." if len(flow['description']) > 60 else flow['description']
        print(f"{name:20} {desc:60}")


def search_command(keyword: str):
    """Search prompts and flows by keyword."""
    from .utils import load_prompt_spec
    from orac.flow import list_flows
    
    print(f"Searching for '{keyword}'...")
    print("=" * 50)
    
    found_any = False
    
    # Search prompts
    prompts_path = Config.get_prompts_dir()
    if prompts_path.exists():
        yaml_files = list(prompts_path.glob('*.yaml')) + list(prompts_path.glob('*.yml'))
        
        matching_prompts = []
        for yaml_file in yaml_files:
            name = yaml_file.stem
            try:
                spec = load_prompt_spec(str(Config.get_prompts_dir()), name)
                # Search in name, description, and prompt text
                search_text = f"{name} {spec.get('description', '')} {spec.get('prompt', '')}".lower()
                if keyword.lower() in search_text:
                    matching_prompts.append((name, spec.get('description', 'No description')))
            except:
                pass
        
        if matching_prompts:
            print(f"\nMatching Prompts ({len(matching_prompts)}):")
            for name, desc in matching_prompts:
                desc = desc[:50] + "..." if len(desc) > 50 else desc
                print(f"  {name:20} {desc}")
            found_any = True
    
    # Search flows
    flows_path = Config.get_flows_dir()
    if flows_path.exists():
        flows = list_flows(str(Config.get_flows_dir()))
        
        matching_flows = []
        for flow in flows:
            # Search in name and description
            search_text = f"{flow['name']} {flow['description']}".lower()
            if keyword.lower() in search_text:
                matching_flows.append((flow['name'], flow['description']))
        
        if matching_flows:
            print(f"\nMatching Flows ({len(matching_flows)}):")
            for name, desc in matching_flows:
                desc = desc[:50] + "..." if len(desc) > 50 else desc
                print(f"  {name:20} {desc}")
            found_any = True
    
    if not found_any:
        print(f"No prompts or flows found matching '{keyword}'")


if __name__ == "__main__":
    main()