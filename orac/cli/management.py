#!/usr/bin/env python3

import argparse
import sys
import os
import getpass

from orac.config import Config


def add_config_parser(subparsers):
    """Add config resource parser."""
    config_parser = subparsers.add_parser(
        'config',
        help='System management',
        description='Manage system configuration'
    )
    
    # Create action subparsers
    config_subparsers = config_parser.add_subparsers(
        dest='action',
        help='Available actions',
        metavar='<action>'
    )
    
    # show action
    show_parser = config_subparsers.add_parser('show', help='Show current configuration')
    
    # set action
    set_parser = config_subparsers.add_parser('set', help='Set configuration value')
    set_parser.add_argument('key', help='Configuration key')
    set_parser.add_argument('value', help='Configuration value')
    
    return config_parser


def add_auth_parser(subparsers):
    """Add auth resource parser."""
    auth_parser = subparsers.add_parser(
        'auth',
        help='Authentication',
        description='Manage authentication and API keys'
    )
    
    # Create action subparsers
    auth_subparsers = auth_parser.add_subparsers(
        dest='action',
        help='Available actions',
        metavar='<action>'
    )
    
    # login action
    login_parser = auth_subparsers.add_parser('login', help='Set up API key')
    login_parser.add_argument('provider', help='Provider name')
    
    # status action
    status_parser = auth_subparsers.add_parser('status', help='Show auth status')
    
    return auth_parser


def handle_config_commands(args, remaining):
    """Handle config resource commands."""
    if args.action == 'show':
        show_config_command()
    elif args.action == 'set':
        set_config_command(args.key, args.value)
    else:
        print(f"Unknown config action: {args.action}", file=sys.stderr)
        sys.exit(1)


def handle_auth_commands(args, remaining):
    """Handle auth resource commands."""
    if args.action == 'login':
        auth_login_command(args.provider)
    elif args.action == 'status':
        auth_status_command()
    else:
        print(f"Unknown auth action: {args.action}", file=sys.stderr)
        sys.exit(1)


def show_config_command():
    """Show current configuration."""
    print("Current Orac Configuration:")
    print("-" * 30)
    
    # Show environment variables
    env_vars = [
        'ORAC_LLM_PROVIDER',
        'ORAC_DEFAULT_MODEL_NAME', 
        'ORAC_LOG_FILE',
        'GOOGLE_API_KEY',
        'OPENAI_API_KEY',
        'ANTHROPIC_API_KEY',
        'AZURE_OPENAI_KEY',
        'OPENROUTER_API_KEY',
    ]
    
    for var in env_vars:
        value = os.getenv(var)
        if value:
            # Mask API keys
            if 'API_KEY' in var or 'KEY' in var:
                display_value = value[:8] + '*' * (len(value) - 8) if len(value) > 8 else '*' * len(value)
            else:
                display_value = value
            print(f"{var}: {display_value}")
        else:
            print(f"{var}: (not set)")
    
    # Show default directories
    print(f"\nDefault directories:")
    print(f"Prompts: {Config.DEFAULT_PROMPTS_DIR}")
    print(f"Flows: {Config.DEFAULT_FLOWS_DIR}")
    print(f"Conversations: {Config.CONVERSATION_DB}")


def set_config_command(key: str, value: str):
    """Set configuration value."""
    # For now, just show what would be set
    # In a full implementation, this might update a config file
    print(f"Would set {key} = {value}")
    print("Note: Currently, configuration is managed via environment variables.")
    print(f"To set {key}, use: export {key}={value}")


def auth_login_command(provider: str):
    """Set up authentication for a provider."""
    provider_vars = {
        'google': 'GOOGLE_API_KEY',
        'openai': 'OPENAI_API_KEY', 
        'anthropic': 'ANTHROPIC_API_KEY',
        'azure': 'AZURE_OPENAI_KEY',
        'openrouter': 'OPENROUTER_API_KEY',
    }
    
    if provider not in provider_vars:
        print(f"Unknown provider: {provider}")
        print(f"Supported providers: {', '.join(provider_vars.keys())}")
        sys.exit(1)
    
    env_var = provider_vars[provider]
    
    print(f"Setting up authentication for {provider}")
    api_key = getpass.getpass(f"Enter your {provider} API key: ")
    
    if api_key:
        print(f"\nTo use this API key, set the environment variable:")
        print(f"export {env_var}={api_key}")
        print(f"export ORAC_LLM_PROVIDER={provider}")
        print("\nAdd these lines to your shell profile (~/.bashrc, ~/.zshrc, etc.) to make them permanent.")
    else:
        print("No API key provided.")


def auth_status_command():
    """Show authentication status."""
    print("Authentication Status:")
    print("-" * 25)
    
    provider = os.getenv('ORAC_LLM_PROVIDER')
    if provider:
        print(f"Current provider: {provider}")
    else:
        print("Current provider: (not set)")
    
    # Check API keys
    providers = {
        'google': 'GOOGLE_API_KEY',
        'openai': 'OPENAI_API_KEY',
        'anthropic': 'ANTHROPIC_API_KEY',
        'azure': 'AZURE_OPENAI_KEY', 
        'openrouter': 'OPENROUTER_API_KEY',
    }
    
    print("\nAPI Key Status:")
    for prov, env_var in providers.items():
        key = os.getenv(env_var)
        status = "✓ Set" if key else "✗ Not set"
        print(f"  {prov:12}: {status}")