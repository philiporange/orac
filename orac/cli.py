#!/usr/bin/env python3

import argparse
import os
import sys
import yaml
import json
from loguru import logger
from dotenv import load_dotenv, find_dotenv
from pathlib import Path
from datetime import datetime

from orac.logger import configure_console_logging
from orac.config import Config
from orac.orac import Orac
from orac.chat import start_chat_interface
from orac.flow import load_flow, FlowEngine, list_flows, FlowValidationError, FlowExecutionError
from orac.skills import load_skill, SkillEngine, list_skills, SkillValidationError, SkillExecutionError
from orac.agent import AgentEngine, load_agent_spec
from orac.registry import ToolRegistry
from orac.config import Provider
from orac.cli_progress import create_cli_reporter


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


# --------------------------------------------------------------------------- #
# Helper functions                                                            #
# --------------------------------------------------------------------------- #
def load_prompt_spec(prompts_dir: str, prompt_name: str) -> dict:
    """
    Return the YAML mapping for *prompt_name*.

    *prompt_name* can be either:
      • a bare name (searched in *prompts_dir*), or
      • a direct path to a *.yaml / *.yml* file.
    """
    if prompt_name.endswith((".yaml", ".yml")) and os.path.isfile(prompt_name):
        path = prompt_name
    else:
        path = os.path.join(prompts_dir, f"{prompt_name}.yaml")

    if not os.path.isfile(path):
        logger.error(f"Prompt '{prompt_name}' not found.")
        print(f"Error: Prompt '{prompt_name}' not found.", file=sys.stderr)
        sys.exit(1)

    logger.debug(f"Loading prompt spec from: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        logger.error(f"Invalid YAML in '{path}'")
        print(f"Error: Invalid YAML in '{path}'", file=sys.stderr)
        sys.exit(1)

    logger.debug(f"Successfully loaded prompt spec with keys: {list(data.keys())}")
    return data


def convert_cli_value(value: str, param_type: str, param_name: str) -> any:
    """Convert CLI string values to appropriate types."""
    logger.debug(
        f"Converting CLI value '{value}' "
        f"to type '{param_type}' "
        f"for parameter '{param_name}'"
    )

    if param_type in ("bool", "boolean"):
        result = value.lower() in ("true", "1", "yes", "on", "y")
        logger.debug(f"Converted to boolean: {result}")
        return result
    elif param_type in ("int", "integer"):
        try:
            result = int(value)
            logger.debug(f"Converted to int: {result}")
            return result
        except ValueError:
            logger.error(f"Parameter '{param_name}' expects an integer, got '{value}'")
            print(
                f"Error: Parameter '{param_name}' expects an integer, got '{value}'",
                file=sys.stderr,
            )
            sys.exit(1)
    elif param_type in ("float", "number"):
        try:
            result = float(value)
            logger.debug(f"Converted to float: {result}")
            return result
        except ValueError:
            logger.error(f"Parameter '{param_name}' expects a number, got '{value}'")
            print(
                f"Error: Parameter '{param_name}' expects a number, got '{value}'",
                file=sys.stderr,
            )
            sys.exit(1)
    elif param_type in ("list", "array"):
        # Parse comma-separated values
        result = [item.strip() for item in value.split(",") if item.strip()]
        logger.debug(f"Converted to list: {result}")
        return result
    else:
        # Default to string
        logger.debug(f"Keeping as string: {value}")
        return value


def format_help_text(param: dict) -> str:
    """Generate enhanced help text for parameters."""
    help_parts = []

    # Base description
    if "description" in param:
        help_parts.append(param["description"])
    else:
        help_parts.append(f"Parameter '{param['name']}'")

    # Type information
    param_type = param.get("type", "string")
    help_parts.append(f"(type: {param_type})")

    # Required/Optional status
    has_default = "default" in param
    is_required = param.get("required", not has_default)

    if is_required and not has_default:
        help_parts.append("REQUIRED")
    elif has_default:
        default_val = param["default"]
        if param_type in ("list", "array") and isinstance(default_val, list):
            default_str = (
                ",".join(map(str, default_val)) if default_val else "empty list"
            )
        else:
            default_str = str(default_val)
        help_parts.append(f"default: {default_str}")

    return " ".join(help_parts)


def add_parameter_argument(parser: argparse.ArgumentParser, param: dict):
    """Add a parameter as a CLI argument with appropriate type handling."""
    name = param["name"]
    arg_name = f"--{name.replace('_', '-')}"
    param_type = param.get("type", "string")

    has_default = "default" in param
    is_required = param.get("required", not has_default)

    help_text = format_help_text(param)

    # Determine if this should be required at CLI level
    cli_required = is_required and not has_default

    if param_type in ("bool", "boolean"):
        # For boolean parameters, use store_true/store_false or allow explicit values
        if has_default:
            default_bool = bool(param["default"])
            if default_bool:
                parser.add_argument(
                    arg_name,
                    dest=name,
                    nargs="?",
                    const="false",  # If flag provided without value, set to false
                    default=None,
                    help=(
                        f"{help_text}. "
                        f"Use --{name.replace('_', '-')} false to override default."
                    ),
                )
            else:
                parser.add_argument(
                    arg_name,
                    dest=name,
                    nargs="?",
                    const="true",  # If flag provided without value, set to true
                    default=None,
                    help=(
                        f"{help_text}. "
                        f"Use --{name.replace('_', '-')} true to override default."
                    ),
                )
        else:
            parser.add_argument(
                arg_name,
                dest=name,
                help=help_text + " (true/false)",
                required=cli_required,
            )
    else:
        parser.add_argument(
            arg_name, dest=name, help=help_text, required=cli_required, default=None
        )


def show_prompt_info(prompts_dir: str, prompt_name: str) -> None:
    """
    Display parameters and defaults for *prompt_name* without touching the LLM
    layer, so it works even when no provider/API key is configured.
    """
    spec = load_prompt_spec(prompts_dir, prompt_name)
    params = spec.get("parameters", [])

    banner = f"Prompt: {prompt_name}"
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
    example = [f"orac prompt run {prompt_name}"]
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

def list_conversations_command(prompts_dir: str):
    """List all conversations in the database."""
    from orac.conversation_db import ConversationDB

    db = ConversationDB(Config.CONVERSATION_DB)
    conversations = db.list_conversations()

    if not conversations:
        print("No conversations found.")
        return

    print(f"\nConversations ({len(conversations)} total):")
    print("-" * 80)
    print(f"{'ID':36} {'Prompt':15} {'Messages':8} {'Updated':20}")
    print("-" * 80)

    for conv in conversations:
        # Format the timestamp
        try:
            dt = datetime.fromisoformat(conv['updated_at'].replace('Z', '+00:00'))
            updated = dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            updated = conv['updated_at'][:19]

        print(f"{conv['id']:36} {conv['prompt_name']:15} {conv['message_count']:8} {updated:20}")

def delete_conversation_command(conversation_id: str):
    """Delete a specific conversation."""
    from orac.conversation_db import ConversationDB

    db = ConversationDB(Config.CONVERSATION_DB)
    if db.conversation_exists(conversation_id):
        db.delete_conversation(conversation_id)
        print(f"Deleted conversation: {conversation_id}")
    else:
        print(f"Conversation not found: {conversation_id}")

def show_conversation_command(conversation_id: str):
    """Show messages from a specific conversation."""
    from orac.conversation_db import ConversationDB

    db = ConversationDB(Config.CONVERSATION_DB)
    messages = db.get_messages(conversation_id)

    if not messages:
        print(f"No messages found for conversation: {conversation_id}")
        return

    print(f"\nConversation: {conversation_id}")
    print("-" * 80)
    for msg in messages:
        role_label = "User" if msg["role"] == "user" else "Assistant"
        print(f"[{msg['timestamp']}] {role_label}:\n{msg['content']}\n")


def add_flow_input_argument(parser: argparse.ArgumentParser, flow_input):
    """Add a flow input as a CLI argument."""
    name = flow_input.name
    arg_name = f"--{name.replace('_', '-')}"
    
    help_parts = []
    if flow_input.description:
        help_parts.append(flow_input.description)
    
    help_parts.append(f"(type: {flow_input.type})")
    
    if flow_input.required and flow_input.default is None:
        help_parts.append("REQUIRED")
    elif flow_input.default is not None:
        help_parts.append(f"default: {flow_input.default}")
    
    help_text = " ".join(help_parts)
    
    cli_required = flow_input.required and flow_input.default is None
    
    parser.add_argument(
        arg_name,
        dest=name,
        help=help_text,
        required=cli_required,
        default=None
    )


def list_flows_command(flows_dir: str):
    """List available flows."""
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


def show_flow_info(flows_dir: str, flow_name: str):
    """Show detailed information about a flow."""
    flow_path = Path(flows_dir) / f"{flow_name}.yaml"
    
    try:
        spec = load_flow(flow_path)
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
    
    # Example usage
    example = [f"orac flow {flow_name}"]
    for inp in spec.inputs:
        if inp.required and inp.default is None:
            flag = f"--{inp.name.replace('_', '-')}"
            example.extend([flag, "'value'"])
    print("Example usage:\n ", " ".join(example))



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
    
    # Add resource parsers
    add_prompt_parser(subparsers)
    add_flow_parser(subparsers)
    add_skill_parser(subparsers)
    add_agent_parser(subparsers)
    add_chat_parser(subparsers)
    add_config_parser(subparsers)
    add_auth_parser(subparsers)
    add_global_commands(subparsers)
    
    # Handle shortcuts and aliases
    args, remaining = handle_shortcuts_and_parse(parser)
    
    # Configure logging
    configure_console_logging(verbose=args.verbose)
    
    # Route to appropriate handler
    if args.resource == 'prompt':
        handle_prompt_commands(args)
    elif args.resource == 'flow':
        handle_flow_commands(args)
    elif args.resource == 'skill':
        handle_skill_commands(args)
    elif args.resource == 'agent':
        handle_agent_commands(args)
    elif args.resource == 'chat':
        handle_chat_commands(args)
    elif args.resource == 'config':  
        handle_config_commands(args)
    elif args.resource == 'auth':
        handle_auth_commands(args)
    elif args.resource in ['list', 'search']:
        handle_global_commands(args)
    else:
        # No resource specified, show help
        parser.print_help()
        sys.exit(1)


def add_prompt_parser(subparsers):
    """Add prompt resource parser."""
    prompt_parser = subparsers.add_parser(
        'prompt', 
        help='Single AI interactions',
        description='Execute, discover, and explore prompts'
    )
    
    # Add common arguments
    add_common_prompt_args(prompt_parser)
    
    # Create action subparsers
    prompt_subparsers = prompt_parser.add_subparsers(
        dest='action',
        help='Available actions',
        metavar='<action>'
    )
    
    # run action
    run_parser = prompt_subparsers.add_parser('run', help='Execute a prompt')
    run_parser.add_argument('name', help='Name of the prompt to run')
    add_prompt_execution_args(run_parser)
    
    # list action
    list_parser = prompt_subparsers.add_parser('list', help='List all available prompts')
    
    # show action
    show_parser = prompt_subparsers.add_parser('show', help='Show prompt details & parameters')
    show_parser.add_argument('name', help='Name of the prompt to show')
    
    # validate action
    validate_parser = prompt_subparsers.add_parser('validate', help='Validate prompt YAML')
    validate_parser.add_argument('name', help='Name of the prompt to validate')
    
    return prompt_parser


def add_flow_parser(subparsers):
    """Add flow resource parser."""
    flow_parser = subparsers.add_parser(
        'flow',
        help='Multi-step AI workflows', 
        description='Execute, discover, and explore flows'
    )
    
    # Add common arguments
    add_common_flow_args(flow_parser)
    
    # Create action subparsers
    flow_subparsers = flow_parser.add_subparsers(
        dest='action',
        help='Available actions',
        metavar='<action>'
    )
    
    # run action
    run_parser = flow_subparsers.add_parser('run', help='Execute a flow')
    run_parser.add_argument('name', help='Name of the flow to run')
    add_flow_execution_args(run_parser)
    
    # list action
    list_parser = flow_subparsers.add_parser('list', help='List all flows')
    
    # show action
    show_parser = flow_subparsers.add_parser('show', help='Show flow structure')
    show_parser.add_argument('name', help='Name of the flow to show')
    
    # graph action
    graph_parser = flow_subparsers.add_parser('graph', help='Show dependency graph')
    graph_parser.add_argument('name', help='Name of the flow to graph')
    
    # test action
    test_parser = flow_subparsers.add_parser('test', help='Dry-run validation')
    test_parser.add_argument('name', help='Name of the flow to test')
    
    return flow_parser


def add_skill_parser(subparsers):
    """Add skill resource parser."""
    skill_parser = subparsers.add_parser(
        'skill',
        help='Runnable skills',
        description='Execute and manage skills'
    )

    # Add common arguments
    add_common_skill_args(skill_parser)

    # Create action subparsers
    skill_subparsers = skill_parser.add_subparsers(
        dest='action',
        help='Available actions',
        metavar='<action>'
    )

    # run action
    run_parser = skill_subparsers.add_parser('run', help='Execute a skill')
    run_parser.add_argument('name', help='Name of the skill to run')
    add_skill_execution_args(run_parser)

    # list action
    list_parser = skill_subparsers.add_parser('list', help='List all available skills')

    # show action
    show_parser = skill_subparsers.add_parser('show', help='Show skill details')
    show_parser.add_argument('name', help='Name of the skill to show')

    # validate action
    validate_parser = skill_subparsers.add_parser('validate', help='Validate skill definition')
    validate_parser.add_argument('name', help='Name of the skill to validate')

    return skill_parser



def add_chat_parser(subparsers):
    """Add chat resource parser."""
    chat_parser = subparsers.add_parser(
        'chat',
        help='Interactive conversations',
        description='Manage interactive conversations'
    )
    
    # Create action subparsers
    chat_subparsers = chat_parser.add_subparsers(
        dest='action',
        help='Available actions',
        metavar='<action>'
    )
    
    # send action
    send_parser = chat_subparsers.add_parser('send', help='Send a message')
    send_parser.add_argument('message', help='Message to send')
    send_parser.add_argument('--conversation-id', help='Use specific conversation')
    add_chat_args(send_parser)
    
    # list action
    list_parser = chat_subparsers.add_parser('list', help='List all conversations')
    
    # show action
    show_parser = chat_subparsers.add_parser('show', help='Show conversation history')
    show_parser.add_argument('conversation_id', help='Conversation ID to show')
    
    # delete action
    delete_parser = chat_subparsers.add_parser('delete', help='Delete conversation')
    delete_parser.add_argument('conversation_id', help='Conversation ID to delete')
    
    # interactive action
    interactive_parser = chat_subparsers.add_parser('interactive', help='Start interactive curses-based chat')
    interactive_parser.add_argument('--conversation-id', help='Use specific conversation')
    interactive_parser.add_argument('--prompt-name', default='chat', help='Prompt to use for chat (default: chat)')
    add_chat_args(interactive_parser)
    
    return chat_parser


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


def add_common_prompt_args(parser):
    """Add common arguments for prompt commands."""
    parser.add_argument(
        '--prompts-dir',
        default=Config.DEFAULT_PROMPTS_DIR,
        help='Directory where prompt YAML files live'
    )
    

def add_common_flow_args(parser):
    """Add common arguments for flow commands."""
    parser.add_argument(
        '--flows-dir',
        default=Config.DEFAULT_FLOWS_DIR,
        help='Directory where flow YAML files live'
    )
    parser.add_argument(
        '--prompts-dir',
        default=Config.DEFAULT_PROMPTS_DIR,
        help='Directory where prompt YAML files live'
    )

def add_common_skill_args(parser):
    """Add common arguments for skill commands."""
    parser.add_argument(
        '--skills-dir',
        default=Config.DEFAULT_SKILLS_DIR,
        help='Directory where skill YAML files live'
    )



def add_prompt_execution_args(parser):
    """Add execution-specific arguments for prompts."""
    # Provider-specific options (global flags already added at top level)
    parser.add_argument('--base-url', help='Custom base URL')
    parser.add_argument('--generation-config', help='JSON string for generation_config')
    
    # File attachments
    parser.add_argument(
        '--file',
        action='append',
        dest='files',
        help='Add file(s) to the request (can be used multiple times)'
    )
    parser.add_argument(
        '--file-url',
        action='append', 
        dest='file_urls',
        help='Download remote file(s) via URL (can be used multiple times)'
    )
    
    # Output options (--output is global, don't duplicate)
    parser.add_argument(
        '--json-output',
        action='store_true',
        help='Format response as JSON'
    )
    parser.add_argument(
        '--response-schema',
        metavar='FILE',
        help='Validate against JSON schema'
    )
    
    # Conversation options (for prompt commands that support conversation mode)
    parser.add_argument('--conversation-id', help='Specify conversation ID')
    parser.add_argument(
        '--reset-conversation',
        action='store_true',
        help='Reset conversation before starting'
    )
    parser.add_argument(
        '--no-save',
        action='store_true',
        help="Don't save messages to conversation history"
    )


def add_flow_execution_args(parser):
    """Add execution-specific arguments for flows."""
    parser.add_argument('--dry-run', action='store_true', help='Show execution plan without running')
    parser.add_argument('--output', '-o', help='Write output to file')
    parser.add_argument('--json-output', action='store_true', help='Format final output as JSON')


def add_skill_execution_args(parser):
    """Add execution-specific arguments for skills."""
    parser.add_argument('--output', '-o', help='Write output to file')
    parser.add_argument('--json-output', action='store_true', help='Format final output as JSON')



def add_chat_args(parser):
    """Add chat-specific arguments."""
    parser.add_argument('--reset-conversation', action='store_true', help='Reset conversation before sending')
    parser.add_argument('--no-save', action='store_true', help="Don't save message to conversation history")
    # Add LLM configuration args
    parser.add_argument('--model-name', help='Override model_name')
    parser.add_argument('--api-key', help='Override API key')
    parser.add_argument(
        '--provider',
        choices=['openai', 'google', 'anthropic', 'azure', 'openrouter', 'custom'],
        help='Select LLM provider'
    )
    parser.add_argument('--base-url', help='Custom base URL')
    parser.add_argument('--generation-config', help='JSON string for generation_config')


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


def handle_prompt_commands(args):
    """Handle prompt resource commands."""
    if args.action == 'run':
        execute_prompt(args)
    elif args.action == 'list':
        list_prompts_command(args.prompts_dir)
    elif args.action == 'show':
        show_prompt_info(args.prompts_dir, args.name)
    elif args.action == 'validate':
        validate_prompt_command(args.prompts_dir, args.name)
    else:
        print(f"Unknown prompt action: {args.action}", file=sys.stderr)
        sys.exit(1)


def handle_flow_commands(args):
    """Handle flow resource commands."""
    if args.action == 'run':
        execute_flow(args)
    elif args.action == 'list':
        list_flows_command(args.flows_dir)
    elif args.action == 'show':
        show_flow_info(args.flows_dir, args.name)
    elif args.action == 'graph':
        show_flow_graph(args.flows_dir, args.name)
    elif args.action == 'test':
        test_flow_command(args.flows_dir, args.name, dry_run=True)
    else:
        print(f"Unknown flow action: {args.action}", file=sys.stderr)
        sys.exit(1)


def handle_skill_commands(args):
    """Handle skill resource commands."""
    if args.action == 'run':
        execute_skill(args)
    elif args.action == 'list':
        list_skills_command(args.skills_dir)
    elif args.action == 'show':
        show_skill_info(args.skills_dir, args.name)
    elif args.action == 'validate':
        validate_skill_command(args.skills_dir, args.name)
    else:
        print(f"Unknown skill action: {args.action}", file=sys.stderr)
        sys.exit(1)



def handle_chat_commands(args):
    """Handle chat resource commands."""
    if args.action == 'send':
        send_chat_message(args)
    elif args.action == 'list':
        list_conversations_command('')
    elif args.action == 'show':
        show_conversation_command(args.conversation_id)
    elif args.action == 'delete':
        delete_conversation_command(args.conversation_id)
    elif args.action == 'interactive':
        handle_chat_interactive(args)
    else:
        print(f"Unknown chat action: {args.action}", file=sys.stderr)
        sys.exit(1)


def handle_config_commands(args):
    """Handle config resource commands."""
    if args.action == 'show':
        show_config_command()
    elif args.action == 'set':
        set_config_command(args.key, args.value)
    else:
        print(f"Unknown config action: {args.action}", file=sys.stderr)
        sys.exit(1)


def handle_auth_commands(args):
    """Handle auth resource commands."""
    if args.action == 'login':
        auth_login_command(args.provider)
    elif args.action == 'status':
        auth_status_command()
    else:
        print(f"Unknown auth action: {args.action}", file=sys.stderr)
        sys.exit(1)


def handle_global_commands(args):
    """Handle global discovery commands."""
    if args.resource == 'list':
        list_all_command()
    elif args.resource == 'search':
        search_command(args.keyword)
    else:
        print(f"Unknown global command: {args.resource}", file=sys.stderr)
        sys.exit(1)


# ==============================================================================
# Command Implementation Functions
# ==============================================================================

def execute_prompt(args):
    """Execute a prompt with dynamic parameter loading."""
    # Load prompt spec to get parameters
    spec = load_prompt_spec(args.prompts_dir, args.name)
    params_spec = spec.get('parameters', [])
    
    # Create a new parser for this specific prompt with its parameters
    prompt_parser = argparse.ArgumentParser(add_help=False)
    add_prompt_execution_args(prompt_parser)
    
    # Add parameters from the prompt spec
    for param in params_spec:
        add_parameter_argument(prompt_parser, param)
    
    # Parse remaining args to get parameter values
    remaining_args = sys.argv[4:]  # Skip 'orac prompt run promptname'
    prompt_args = prompt_parser.parse_args(remaining_args)
    
    # Parse JSON overrides
    def _safe_json(label: str, s: str):
        try:
            return json.loads(s)
        except Exception as e:
            logger.error(f"{label} JSON parse error: {e}")
            print(f"Error: {label} is not valid JSON: {e}", file=sys.stderr)
            sys.exit(1)

    gen_config = (
        _safe_json("generation_config", prompt_args.generation_config)
        if getattr(prompt_args, 'generation_config', None)
        else {}
    )

    # Structured output injection
    if getattr(prompt_args, 'json_output', False):
        gen_config = gen_config or {}
        gen_config["response_mime_type"] = "application/json"

    if getattr(prompt_args, 'response_schema', None):
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
    param_values = {}
    for param in params_spec:
        name = param["name"]
        cli_value = getattr(prompt_args, name, None)
        param_type = param.get("type", "string")

        if cli_value is not None:
            converted_value = convert_cli_value(cli_value, param_type, name)
            param_values[name] = converted_value

    logger.debug(f"Final parameter values: {param_values}")

    # Create Orac instance and execute
    try:
        logger.debug("Creating Orac instance")
        
        # Create progress reporter if not quiet
        progress_callback = None
        if not args.quiet:
            reporter = create_cli_reporter(verbose=args.verbose, quiet=args.quiet)
            progress_callback = reporter.report
        
        wrapper = Orac(
            prompt_name=args.name,
            prompts_dir=args.prompts_dir,
            model_name=args.model_name,
            api_key=args.api_key,
            generation_config=gen_config or None,
            verbose=args.verbose,
            files=getattr(prompt_args, 'files', None),
            file_urls=getattr(prompt_args, 'file_urls', None),
            provider=args.provider,
            base_url=getattr(prompt_args, 'base_url', None),
            conversation_id=getattr(prompt_args, 'conversation_id', None),
            auto_save=not getattr(prompt_args, 'no_save', False),
            progress_callback=progress_callback,
        )

        # Reset conversation if requested
        if getattr(prompt_args, 'reset_conversation', False):
            wrapper.reset_conversation()
            logger.info("Reset conversation history")

        logger.debug("Calling completion method")
        result = wrapper.completion(**param_values)

        # Output result
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


def execute_flow(args):
    """Execute a flow with dynamic parameter loading."""
    flow_path = Path(args.flows_dir) / f"{args.name}.yaml"
    
    try:
        spec = load_flow(flow_path)
        
        # Create a new parser for this specific flow with its parameters
        flow_parser = argparse.ArgumentParser(add_help=False)
        add_flow_execution_args(flow_parser)
        
        # Add flow inputs as parameters
        for flow_input in spec.inputs:
            add_flow_input_argument(flow_parser, flow_input)
        
        # Parse remaining args
        remaining_args = sys.argv[4:]  # Skip 'orac flow run flowname'
        flow_args = flow_parser.parse_args(remaining_args)
        
        # Create progress reporter if not quiet
        progress_callback = None
        if not args.quiet:
            reporter = create_cli_reporter(verbose=args.verbose, quiet=args.quiet)
            progress_callback = reporter.report
        
        engine = FlowEngine(spec, prompts_dir=args.prompts_dir, progress_callback=progress_callback)
        
        # Collect input values from CLI args
        inputs = {}
        for flow_input in spec.inputs:
            cli_value = getattr(flow_args, flow_input.name, None)
            if cli_value is not None:
                # Convert CLI string to appropriate type
                converted_value = convert_cli_value(cli_value, flow_input.type, flow_input.name)
                inputs[flow_input.name] = converted_value
            elif flow_input.default is not None:
                inputs[flow_input.name] = flow_input.default
        
        logger.debug(f"Flow inputs: {inputs}")
        
        # Execute flow
        results = engine.execute(inputs, dry_run=getattr(flow_args, 'dry_run', False))
        
        if getattr(flow_args, 'dry_run', False):
            print("DRY RUN - Flow execution plan:")
            print(f"Execution order: {' -> '.join(engine.execution_order)}")
            return
        
        # Output results
        if args.output:
            try:
                with open(args.output, "w", encoding="utf-8") as f:
                    if getattr(flow_args, 'json_output', False):
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
            if getattr(flow_args, 'json_output', False):
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


def list_prompts_command(prompts_dir: str):
    """List available prompts."""
    from pathlib import Path
    
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


def validate_prompt_command(prompts_dir: str, prompt_name: str):
    """Validate prompt YAML."""
    try:
        spec = load_prompt_spec(prompts_dir, prompt_name)
        print(f"✓ Prompt '{prompt_name}' is valid")
        
        # Check for required fields
        if 'prompt' not in spec:
            print("⚠ Warning: No 'prompt' field found")
        
        if 'parameters' in spec:
            params = spec['parameters']
            if not isinstance(params, list):
                print("⚠ Warning: 'parameters' should be a list")
            else:
                for i, param in enumerate(params):
                    if not isinstance(param, dict):
                        print(f"⚠ Warning: Parameter {i} should be a dictionary")
                    elif 'name' not in param:
                        print(f"⚠ Warning: Parameter {i} missing 'name' field")
        
        print(f"Validation complete for '{prompt_name}'")
        
    except Exception as e:
        print(f"✗ Validation failed for '{prompt_name}': {e}")
        sys.exit(1)


def show_flow_graph(flows_dir: str, flow_name: str):
    """Show dependency graph for a flow."""
    flow_path = Path(flows_dir) / f"{flow_name}.yaml"
    
    try:
        spec = load_flow(flow_path)
        engine = FlowEngine(spec, prompts_dir=Config.DEFAULT_PROMPTS_DIR)
        
        print(f"\nDependency graph for flow '{flow_name}':")
        print("-" * 50)
        print(f"Execution order: {' -> '.join(engine.execution_order)}")
        
        print("\nStep dependencies:")
        for step_name, step in spec.steps.items():
            if step.depends_on:
                deps = ', '.join(step.depends_on)
                print(f"  {step_name} depends on: {deps}")
            else:
                print(f"  {step_name} (no dependencies)")
                
    except (FlowValidationError, FlowExecutionError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def test_flow_command(flows_dir: str, flow_name: str, dry_run=True):
    """Test/validate a flow with dry run."""
    flow_path = Path(flows_dir) / f"{flow_name}.yaml"
    
    try:
        spec = load_flow(flow_path)
        engine = FlowEngine(spec, prompts_dir=Config.DEFAULT_PROMPTS_DIR)
        
        print(f"\n✓ Flow '{flow_name}' validation successful")
        print(f"Steps: {len(spec.steps)}")
        print(f"Inputs: {len(spec.inputs)}")
        print(f"Outputs: {len(spec.outputs)}")
        print(f"Execution order: {' -> '.join(engine.execution_order)}")
        
        # Test with empty inputs to validate structure
        test_inputs = {}
        for inp in spec.inputs:
            if inp.default is not None:
                test_inputs[inp.name] = inp.default
        
        if dry_run:
            print("\nDry run test passed - flow structure is valid")
        
    except (FlowValidationError, FlowExecutionError) as e:
        print(f"✗ Flow test failed: {e}", file=sys.stderr)
        sys.exit(1)


def handle_chat_interactive(args):
    """Start interactive curses-based chat interface."""
    # Parse generation config if provided
    gen_config = None
    if getattr(args, 'generation_config', None):
        try:
            gen_config = json.loads(args.generation_config) 
        except Exception as e:
            print(f"Error: generation_config is not valid JSON: {e}", file=sys.stderr)
            sys.exit(1)
    
    try:
        # Prepare arguments for the Orac instance
        # Note: use_conversation is hardcoded to True in start_chat_interface, so don't pass it here
        orac_kwargs = {
            'model_name': args.model_name,
            'api_key': args.api_key,  
            'provider': args.provider,
            'base_url': getattr(args, 'base_url', None),
            'generation_config': gen_config,
            'auto_save': not getattr(args, 'no_save', False),
        }
        
        # Remove None values to avoid passing them to Orac
        orac_kwargs = {k: v for k, v in orac_kwargs.items() if v is not None}
        
        # Start the interactive chat interface
        start_chat_interface(
            prompt_name=args.prompt_name,
            conversation_id=getattr(args, 'conversation_id', None),
            **orac_kwargs
        )
        
    except Exception as e:
        logger.error(f"Error starting interactive chat: {e}")
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def send_chat_message(args):
    """Send a chat message."""
    # Parse generation config if provided
    gen_config = None
    if getattr(args, 'generation_config', None):
        try:
            gen_config = json.loads(args.generation_config) 
        except Exception as e:
            print(f"Error: generation_config is not valid JSON: {e}", file=sys.stderr)
            sys.exit(1)
    
    # Create a simple chat prompt if needed
    try:
        from orac.orac import Orac
        
        # Create progress reporter if not quiet
        progress_callback = None
        if not args.quiet:
            reporter = create_cli_reporter(verbose=args.verbose, quiet=args.quiet)
            progress_callback = reporter.report
        
        wrapper = Orac(
            prompt_name='chat',  # Assume a 'chat' prompt exists
            model_name=args.model_name,
            api_key=args.api_key,
            provider=args.provider,
            base_url=getattr(args, 'base_url', None),
            generation_config=gen_config,
            conversation_id=getattr(args, 'conversation_id', None),
            auto_save=not getattr(args, 'no_save', False),
            progress_callback=progress_callback,
        )
        
        # Reset conversation if requested
        if getattr(args, 'reset_conversation', False):
            wrapper.reset_conversation()
            logger.info("Reset conversation history")
        
        result = wrapper.completion(message=args.message)
        
        # Output result
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
        
    except Exception as e:
        logger.error(f"Error sending chat message: {e}")
        print(f"Error: {e}", file=sys.stderr)
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
    import getpass
    
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


def list_all_command():
    """List all prompts and flows."""
    print("All Available Resources:")
    print("=" * 50)
    
    # List prompts
    print("\nPROMPTS:")
    list_prompts_command(Config.DEFAULT_PROMPTS_DIR)
    
    # List flows
    print("\nFLOWS:")
    list_flows_command(Config.DEFAULT_FLOWS_DIR)


def search_command(keyword: str):
    """Search prompts and flows by keyword."""
    print(f"Searching for '{keyword}'...")
    print("=" * 50)
    
    found_any = False
    
    # Search prompts
    prompts_path = Path(Config.DEFAULT_PROMPTS_DIR)
    if prompts_path.exists():
        yaml_files = list(prompts_path.glob('*.yaml')) + list(prompts_path.glob('*.yml'))
        
        matching_prompts = []
        for yaml_file in yaml_files:
            name = yaml_file.stem
            try:
                spec = load_prompt_spec(Config.DEFAULT_PROMPTS_DIR, name)
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
    flows_path = Path(Config.DEFAULT_FLOWS_DIR)
    if flows_path.exists():
        flows = list_flows(Config.DEFAULT_FLOWS_DIR)
        
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

def execute_skill(args):
    """Execute a skill with dynamic parameter loading."""
    skill_path = Path(args.skills_dir) / f"{args.name}.yaml"
    try:
        spec = load_skill(skill_path)
        # Create a new parser for this specific skill with its parameters
        skill_parser = argparse.ArgumentParser(add_help=False)
        add_skill_execution_args(skill_parser)
        # Add skill inputs as parameters
        for skill_input in spec.inputs:
            add_parameter_argument(skill_parser, skill_input.__dict__)
        # Parse remaining args
        remaining_args = sys.argv[4:]  # Skip 'orac skill run skillname'
        skill_args = skill_parser.parse_args(remaining_args)
        # Create progress reporter if not quiet
        progress_callback = None
        if not args.quiet:
            reporter = create_cli_reporter(verbose=args.verbose, quiet=args.quiet)
            progress_callback = reporter.report
        engine = SkillEngine(spec, skills_dir=args.skills_dir, progress_callback=progress_callback)
        # Collect input values from CLI args
        inputs = {}
        for skill_input in spec.inputs:
            cli_value = getattr(skill_args, skill_input.name, None)
            if cli_value is not None:
                # Convert CLI string to appropriate type
                converted_value = convert_cli_value(cli_value, skill_input.type, skill_input.name)
                inputs[skill_input.name] = converted_value
            elif skill_input.default is not None:
                inputs[skill_input.name] = skill_input.default
        logger.debug(f"Skill inputs: {inputs}")
        # Execute skill
        results = engine.execute(inputs)
        # Output results
        if args.output:
            try:
                with open(args.output, "w", encoding="utf-8") as f:
                    if getattr(skill_args, 'json_output', False):
                        json.dump(results, f, indent=2)
                    else:
                        print(results, file=f)
                logger.info(f"Skill output written to file: {args.output}")
            except IOError as e:
                logger.error(f"Error writing to output file '{args.output}': {e}")
                print(f"Error writing to output file '{args.output}': {e}", file=sys.stderr)
                sys.exit(1)
        else:
            if getattr(skill_args, 'json_output', False):
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

def list_skills_command(skills_dir: str):
    """List available skills."""
    skills = list_skills(skills_dir)
    if not skills:
        print(f"No skills found in {skills_dir}")
        return
    print(f"\nAvailable skills ({len(skills)} total):")
    print("-" * 80)
    print(f"{'Name':20} {'Description':60}")
    print("-" * 80)
    for skill in skills:
        name = skill['name']
        desc = skill['description'][:57] + "..." if len(skill['description']) > 60 else skill['description']
        print(f"{name:20} {desc:60}")

def show_skill_info(skills_dir: str, skill_name: str):
    """Show detailed information about a skill."""
    skill_path = Path(skills_dir) / f"{skill_name}.yaml"
    try:
        spec = load_skill(skill_path)
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
    # Example usage
    example = [f"orac skill run {skill_name}"]
    for inp in spec.inputs:
        if inp.required and inp.default is None:
            flag = f"--{inp.name.replace('_', '-')}"
            example.extend([flag, "'value'"])
    print("Example usage:\n ", " ".join(example))

def validate_skill_command(skills_dir: str, skill_name: str):
    """Validate skill YAML."""
    try:
        skill_path = Path(skills_dir) / f"{skill_name}.yaml"
        spec = load_skill(skill_path)
        print(f"✓ Skill '{skill_name}' is valid")
        # Check for required fields
        if 'name' not in spec.__dict__:
            print("⚠ Warning: No 'name' field found")
        if 'description' not in spec.__dict__:
            print("⚠ Warning: No 'description' field found")
        if 'inputs' not in spec.__dict__:
            print("⚠ Warning: No 'inputs' field found")
        if 'outputs' not in spec.__dict__:
            print("⚠ Warning: No 'outputs' field found")
        print(f"Validation complete for '{skill_name}'")
    except Exception as e:
        print(f"✗ Validation failed for '{skill_name}': {e}")
        sys.exit(1)


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


def handle_agent_commands(args):
    """Handle agent resource commands."""
    if args.action == 'run':
        execute_agent(args)
    else:
        print(f"Unknown agent action: {args.action}", file=sys.stderr)
        sys.exit(1)


def execute_agent(args):
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
        
    # Parse remaining args to get parameter values
    remaining_args = sys.argv[4:] # Skips 'orac agent run agentname'
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
        engine = AgentEngine(spec, registry, provider, api_key)
        
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


if __name__ == "__main__":
    main()
