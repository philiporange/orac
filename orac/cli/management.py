#!/usr/bin/env python3

import argparse
import sys
import os
import getpass
import json

from orac.config import Config, Provider
from orac.auth import AuthManager
from orac.client import Client


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
    """Add auth resource parser with enhanced consent management."""
    auth_parser = subparsers.add_parser(
        'auth',
        help='Manage authentication and API access',
        description='''
Manage authentication, API keys, and consent for LLM providers.

Orac requires explicit consent before accessing environment variables for API keys.
This ensures no unexpected API charges and gives you full control over data access.

Common workflows:
  orac auth init                    # Interactive setup (recommended)
  orac auth login openai --allow-env # Quick setup with environment access
  orac auth status                  # Check current authentication status
  orac auth consent show            # View consent permissions
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    # Create action subparsers
    auth_subparsers = auth_parser.add_subparsers(
        dest='action',
        help='Available actions',
        metavar='<action>'
    )
    
    # Enhanced login with consent
    login_parser = auth_subparsers.add_parser(
        'login', 
        help='Setup authentication for a specific provider',
        description='''
Setup authentication for a specific LLM provider.

Examples:
  orac auth login openai --allow-env         # Use OPENAI_API_KEY from environment
  orac auth login openai --api-key sk-...    # Use direct API key
  orac auth login azure --api-key-env MY_KEY # Use custom environment variable
  orac auth login custom --base-url https://api.example.com/v1/
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    login_parser.add_argument('provider', 
        help='Provider name (openai, google, anthropic, azure, openrouter, custom)')
    login_parser.add_argument('--api-key', 
        help='Direct API key (secure, no environment access needed)')
    login_parser.add_argument('--api-key-env', 
        help='Custom environment variable name for API key')
    login_parser.add_argument('--allow-env', action='store_true', 
        help='Allow reading from default environment variable (requires consent)')
    login_parser.add_argument('--base-url', 
        help='Custom base URL (required for custom provider)')
    login_parser.add_argument('--model-name', 
        help='Default model name for this provider')
    
    # Consent management
    consent_parser = auth_subparsers.add_parser(
        'consent', 
        help='Manage environment variable access consent',
        description='''
Manage consent for accessing environment variables containing API keys.

Orac requires explicit consent before reading environment variables to ensure
no unexpected API charges and give you full control over data access.

Examples:
  orac auth consent show              # View all consent permissions
  orac auth consent grant openai      # Allow access to OPENAI_API_KEY
  orac auth consent revoke google     # Revoke access to GOOGLE_API_KEY
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    consent_subparsers = consent_parser.add_subparsers(
        dest='consent_action',
        help='Consent actions',
        metavar='<action>'
    )
    consent_subparsers.add_parser('show', help='Show consent status for all providers')
    
    revoke_parser = consent_subparsers.add_parser(
        'revoke', 
        help='Revoke environment access consent for a provider'
    )
    revoke_parser.add_argument('provider', help='Provider to revoke consent for (openai, google, etc.)')
    
    grant_parser = consent_subparsers.add_parser(
        'grant', 
        help='Grant environment access consent for a provider'
    )
    grant_parser.add_argument('provider', help='Provider to grant consent for (openai, google, etc.)')
    
    # Multi-provider setup
    init_parser = auth_subparsers.add_parser(
        'init', 
        help='Interactive authentication setup (recommended)',
        description='''
Interactive authentication setup wizard.

This is the easiest way to get started with Orac. It will:
  1. Detect available API keys in your environment
  2. Guide you through granting consent for each provider
  3. Set up a default provider for new projects
  4. Test the connection to ensure everything works

Examples:
  orac auth init                           # Full interactive setup
  orac auth init --default-provider openai # Use OpenAI as default
  orac auth init --non-interactive         # Batch mode (no prompts)
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    init_parser.add_argument('--non-interactive', action='store_true', 
        help='Non-interactive mode (will fail if consent needed)')
    init_parser.add_argument('--default-provider', default='openrouter', 
        help='Default provider to recommend (default: openrouter)')
    
    # Status action
    status_parser = auth_subparsers.add_parser(
        'status', 
        help='Show comprehensive authentication status',
        description='''
Show detailed authentication status including:
  • Which providers have consent granted
  • Which API keys are accessible
  • Current default provider settings
  • Consent file location and permissions

This is useful for troubleshooting authentication issues.
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
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
    """Handle auth resource commands with enhanced consent management."""
    if args.action == 'login':
        auth_login_command_v2(args)
    elif args.action == 'consent':
        handle_consent_commands(args)
    elif args.action == 'init':
        auth_init_command(args)
    elif args.action == 'status':
        auth_status_command_v2()
    elif args.action is None:
        # No action specified, show help
        print("❌ Please specify an auth action. Here are the available options:\n", file=sys.stderr)
        print("🚀 Quick start (recommended):")
        print("   orac auth init                    # Interactive setup wizard")
        print()
        print("📋 Individual commands:")
        print("   orac auth status                  # Check authentication status")
        print("   orac auth login <provider>        # Setup specific provider")
        print("   orac auth consent show            # View consent permissions")
        print()
        print("💡 For detailed help: orac auth --help")
        sys.exit(1)
    else:
        print(f"❌ Unknown auth action: '{args.action}'", file=sys.stderr)
        print("💡 Available actions: login, consent, init, status")
        print("💡 For help: orac auth --help")
        sys.exit(1)


def handle_consent_commands(args):
    """Handle consent subcommands."""
    if args.consent_action == 'show':
        consent_show_command()
    elif args.consent_action == 'revoke':
        consent_revoke_command(args.provider)
    elif args.consent_action == 'grant':
        consent_grant_command(args.provider)
    else:
        print(f"Unknown consent action: {args.consent_action}", file=sys.stderr)
        sys.exit(1)


def show_config_command():
    """Show current configuration using new Config methods."""
    print("Current Orac Configuration:")
    print("=" * 40)
    
    print("\nConfiguration Directories:")
    print(f"  Prompts:       {Config.get_prompts_dir()}")
    print(f"  Flows:         {Config.get_flows_dir()}")
    print(f"  Skills:        {Config.get_skills_dir()}")
    print(f"  Agents:        {Config.get_agents_dir()}")
    print(f"  Config File:   {Config.get_config_file()}")
    
    print(f"\nLogging:")
    print(f"  Log File:      {Config.get_log_file_path()}")
    
    print(f"\nConversation:")
    print(f"  Database:      {Config.get_conversation_db_path()}")
    print(f"  Default Mode:  {Config.get_default_conversation_mode()}")
    print(f"  Max History:   {Config.get_max_conversation_history()}")
    
    print(f"\nModel Defaults:")
    print(f"  Model Name:    {Config.get_default_model_name()}")
    
    # Show provider from environment (but note it's not used automatically)
    provider = Config.get_provider_from_env()
    print(f"\nEnvironment Provider (not auto-loaded): {provider.value if provider else '(not set)'}")
    
    print("\nNote: Environment variables are only accessed with explicit consent.")


def set_config_command(key: str, value: str):
    """Set configuration value."""
    # For now, just show what would be set
    # In a full implementation, this might update a config file
    print(f"Configuration setting: {key} = {value}")
    print("\nNote: Most configuration is now managed via:")
    print("1. YAML configuration files")
    print("2. Runtime parameters")
    print("3. Environment variables (with explicit consent)")
    print(f"\nTo set environment variable: export {key}={value}")


def auth_login_command_v2(args):
    """Enhanced authentication setup with consent management."""
    try:
        provider = Provider(args.provider.lower())
    except ValueError:
        print(f"Unknown provider: {args.provider}")
        print(f"Supported providers: {', '.join([p.value for p in Provider])}")
        sys.exit(1)
    
    auth_manager = AuthManager()
    
    print(f"\n🔐 Setting up authentication for {provider.value.title()}")
    print("=" * 50)
    
    try:
        # If direct API key provided, no consent needed
        if args.api_key:
            print("✓ Using provided API key (no consent required)")
            
        # If custom environment variable specified
        elif args.api_key_env:
            key_value = os.getenv(args.api_key_env)
            if not key_value:
                print(f"❌ Environment variable {args.api_key_env} is not set")
                sys.exit(1)
            print(f"✓ Using API key from {args.api_key_env}")
            
        # If allow environment access (requires consent)
        elif args.allow_env:
            if not auth_manager.request_consent(provider, interactive=True):
                print("❌ Consent denied. Cannot access environment variables.")
                sys.exit(1)
            print(f"✓ Consent granted for {provider.value} environment access")
            
        else:
            print("❌ No API key source specified.")
            print("\nOptions:")
            print("  --api-key KEY           # Direct API key")
            print("  --api-key-env VAR       # Read from environment variable")
            print("  --allow-env             # Read from default env var (with consent)")
            sys.exit(1)
        
        # Test the configuration by creating a client
        client = Client()
        client.add_provider(
            provider,
            api_key=args.api_key,
            api_key_env=args.api_key_env,
            allow_env=args.allow_env,
            base_url=args.base_url,
            model_name=args.model_name,
            interactive=False  # Don't prompt again
        )
        
        print(f"✅ Successfully configured {provider.value}")
        print(f"   Default model: {client.get_provider_registry().get_model_name(provider)}")
        
        if provider == client.get_default_provider():
            print(f"   Set as default provider")
        
        print(f"\n💡 You can now use: orac prompt run <prompt_name> --provider {provider.value}")
        
    except Exception as e:
        print(f"❌ Failed to setup {provider.value}: {e}")
        sys.exit(1)


def consent_show_command():
    """Show consent status for all providers."""
    auth_manager = AuthManager()
    status = auth_manager.show_consent_status()
    
    print("\n🔒 Consent Status")
    print("=" * 30)
    print(f"Consent file: {status['consent_file']}")
    print()
    
    for provider_name, info in status['providers'].items():
        icon = "✅" if info['consent_granted'] else "❌"
        print(f"{icon} {provider_name.title()}")
        if info['consent_granted']:
            print(f"   Granted: {info['consent_timestamp']}")
            if info['api_key_env']:
                print(f"   Environment: {info['api_key_env']}")
        print()


def consent_revoke_command(provider_name: str):
    """Revoke consent for a provider."""
    try:
        provider = Provider(provider_name.lower())
    except ValueError:
        print(f"Unknown provider: {provider_name}")
        sys.exit(1)
    
    auth_manager = AuthManager()
    if auth_manager.revoke_consent(provider):
        print(f"✅ Revoked consent for {provider.value}")
        print("   Environment variable access is no longer permitted")
    else:
        print(f"ℹ️ No consent was previously granted for {provider.value}")


def consent_grant_command(provider_name: str):
    """Grant consent for a provider."""
    try:
        provider = Provider(provider_name.lower())
    except ValueError:
        print(f"Unknown provider: {provider_name}")
        sys.exit(1)
    
    auth_manager = AuthManager()
    auth_manager.grant_consent(provider)
    print(f"✅ Granted consent for {provider.value}")
    print("   Environment variable access is now permitted")


def auth_init_command(args):
    """Interactive initialization with multiple providers."""
    print("\n🚀 Orac Authentication Initialization")
    print("=" * 45)
    
    auth_manager = AuthManager()
    client = Client(auth_manager)
    
    interactive = not args.non_interactive
    default_provider_str = args.default_provider.lower()
    
    try:
        default_provider = Provider(default_provider_str)
    except ValueError:
        print(f"Invalid default provider: {default_provider_str}")
        sys.exit(1)
    
    if interactive:
        print("This will set up Orac with your preferred LLM providers.")
        print("OpenRouter is recommended as it provides access to multiple models.")
        print()
        
        setup_default = input(f"Setup {default_provider.value.title()} as default provider? [Y/n]: ")
        if setup_default.lower() not in ('n', 'no'):
            try:
                client.add_provider(default_provider, allow_env=True, interactive=True)
                client.set_default_provider(default_provider)
                print(f"✅ {default_provider.value.title()} configured as default")
            except Exception as e:
                print(f"❌ Failed to setup {default_provider.value}: {e}")
                if "consent" in str(e).lower():
                    print("   Consent was denied or environment variable not found")
        
        # Ask about additional providers
        print("\nWould you like to add additional providers?")
        other_providers = [p for p in Provider if p != default_provider]
        for provider in other_providers:
            add_provider = input(f"Add {provider.value.title()}? [y/N]: ")
            if add_provider.lower() in ('y', 'yes'):
                try:
                    client.add_provider(provider, allow_env=True, interactive=True)
                    print(f"✅ {provider.value.title()} configured")
                except Exception as e:
                    print(f"❌ Failed to setup {provider.value}: {e}")
                    continue
    
    else:
        # Non-interactive mode
        try:
            client.add_provider(default_provider, allow_env=True, interactive=False)
            client.set_default_provider(default_provider)
            print(f"✅ {default_provider.value.title()} configured (non-interactive)")
        except Exception as e:
            print(f"❌ Failed non-interactive setup: {e}")
            print("   Try interactive mode: orac auth init")
            sys.exit(1)
    
    # Show final status
    if client.is_initialized():
        print(f"\n🎉 Initialization complete!")
        print(f"   Default provider: {client.get_default_provider().value}")
        print(f"   Configured providers: {len(client.get_registered_providers())}")
        print("\n💡 You can now run: orac prompt run <prompt_name>")
    else:
        print("\n❌ No providers were successfully configured")
        print("   Try: orac auth login <provider> --allow-env")


def auth_status_command_v2():
    """Show comprehensive authentication status."""
    print("\n📊 Authentication Status")
    print("=" * 35)
    
    # Show consent status
    auth_manager = AuthManager()
    consent_status = auth_manager.show_consent_status()
    
    print("Consent Status:")
    consented_providers = []
    for provider_name, info in consent_status['providers'].items():
        icon = "✅" if info['consent_granted'] else "❌"
        print(f"  {icon} {provider_name.title()}")
        if info['consent_granted']:
            consented_providers.append(provider_name)
    
    print(f"\nConsented providers: {len(consented_providers)}")
    print(f"Consent file: {consent_status['consent_file']}")
    
    # Try to create a client to show what's actually working
    print("\nProvider Accessibility:")
    for provider in Provider:
        try:
            test_client = Client(auth_manager)
            test_client.add_provider(provider, allow_env=True, interactive=False)
            print(f"  ✅ {provider.value.title()}: Ready")
        except Exception as e:
            error_msg = str(e)
            if "consent" in error_msg.lower():
                print(f"  🔒 {provider.value.title()}: Consent required")
            elif "not found" in error_msg.lower():
                print(f"  ❌ {provider.value.title()}: API key not found")
            else:
                print(f"  ❌ {provider.value.title()}: {error_msg}")
    
    print(f"\n💡 To grant consent: orac auth consent grant <provider>")
    print(f"💡 To setup provider: orac auth login <provider> --allow-env")