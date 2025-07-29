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
from orac.workflow import load_workflow, WorkflowEngine, list_workflows, WorkflowValidationError, WorkflowExecutionError


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
    example = [f"python -m orac {prompt_name}"]
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


def add_workflow_input_argument(parser: argparse.ArgumentParser, workflow_input):
    """Add a workflow input as a CLI argument."""
    name = workflow_input.name
    arg_name = f"--{name.replace('_', '-')}"
    
    help_parts = []
    if workflow_input.description:
        help_parts.append(workflow_input.description)
    
    help_parts.append(f"(type: {workflow_input.type})")
    
    if workflow_input.required and workflow_input.default is None:
        help_parts.append("REQUIRED")
    elif workflow_input.default is not None:
        help_parts.append(f"default: {workflow_input.default}")
    
    help_text = " ".join(help_parts)
    
    cli_required = workflow_input.required and workflow_input.default is None
    
    parser.add_argument(
        arg_name,
        dest=name,
        help=help_text,
        required=cli_required,
        default=None
    )


def list_workflows_command(workflows_dir: str):
    """List available workflows."""
    workflows = list_workflows(workflows_dir)
    
    if not workflows:
        print(f"No workflows found in {workflows_dir}")
        return
    
    print(f"\nAvailable workflows ({len(workflows)} total):")
    print("-" * 80)
    print(f"{'Name':20} {'Description':60}")
    print("-" * 80)
    
    for workflow in workflows:
        name = workflow['name']
        desc = workflow['description'][:57] + "..." if len(workflow['description']) > 60 else workflow['description']
        print(f"{name:20} {desc:60}")


def show_workflow_info(workflows_dir: str, workflow_name: str):
    """Show detailed information about a workflow."""
    workflow_path = Path(workflows_dir) / f"{workflow_name}.yaml"
    
    try:
        spec = load_workflow(workflow_path)
    except WorkflowValidationError as e:
        print(f"Error loading workflow: {e}", file=sys.stderr)
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
    example = [f"orac workflow {workflow_name}"]
    for inp in spec.inputs:
        if inp.required and inp.default is None:
            flag = f"--{inp.name.replace('_', '-')}"
            example.extend([flag, "'value'"])
    print("Example usage:\n ", " ".join(example))


def run_workflow_command(args):
    """Execute a workflow."""
    workflows_dir = args.workflows_dir
    workflow_name = args.workflow_name
    workflow_path = Path(workflows_dir) / f"{workflow_name}.yaml"
    
    try:
        spec = load_workflow(workflow_path)
        engine = WorkflowEngine(spec, prompts_dir=args.prompts_dir)
        
        # Collect input values from CLI args
        inputs = {}
        for workflow_input in spec.inputs:
            cli_value = getattr(args, workflow_input.name, None)
            if cli_value is not None:
                # Convert CLI string to appropriate type
                converted_value = convert_cli_value(cli_value, workflow_input.type, workflow_input.name)
                inputs[workflow_input.name] = converted_value
            elif workflow_input.default is not None:
                inputs[workflow_input.name] = workflow_input.default
        
        logger.debug(f"Workflow inputs: {inputs}")
        
        # Execute workflow
        results = engine.execute(inputs, dry_run=args.dry_run)
        
        if args.dry_run:
            print("DRY RUN - Workflow execution plan:")
            print(f"Execution order: {' -> '.join(engine.execution_order)}")
            return
        
        # Output results
        if args.output:
            try:
                with open(args.output, "w", encoding="utf-8") as f:
                    if args.json_output:
                        json.dump(results, f, indent=2)
                    else:
                        for name, value in results.items():
                            f.write(f"{name}: {value}\n")
                logger.info(f"Workflow output written to file: {args.output}")
            except IOError as e:
                logger.error(f"Error writing to output file '{args.output}': {e}")
                print(f"Error writing to output file '{args.output}': {e}", file=sys.stderr)
                sys.exit(1)
        else:
            if args.json_output:
                print(json.dumps(results, indent=2))
            else:
                for name, value in results.items():
                    print(f"{name}: {value}")
        
        logger.info("Workflow completed successfully")
        
    except (WorkflowValidationError, WorkflowExecutionError) as e:
        logger.error(f"Workflow error: {e}")
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error running workflow: {e}")
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    # Check if we're using the new subcommand interface or legacy mode
    # Legacy mode: first arg is prompt name (not 'workflow')
    # New mode: first arg is 'workflow' 
    
    if len(sys.argv) > 1 and sys.argv[1] == "workflow":
        # New workflow subcommand interface
        run_workflow_interface()
    else:
        # Legacy prompt interface (backward compatibility)
        run_prompt_interface()


def run_workflow_interface():
    """Handle workflow subcommand interface."""
    # We need to handle the fact that 'workflow' might be in sys.argv
    argv = sys.argv[1:]
    if argv and argv[0] == 'workflow':
        argv = argv[1:]

    # Main parser
    parser = argparse.ArgumentParser(
        prog="orac workflow",
        description="Execute workflows - chains of prompts with data flow"
    )
    
    # Global flags
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging output"
    )
    parser.add_argument(
        "--workflows-dir", default=Config.DEFAULT_WORKFLOWS_DIR, help="Directory where workflow YAML files live"
    )
    parser.add_argument(
        "--prompts-dir", default=Config.DEFAULT_PROMPTS_DIR, help="Directory where prompt YAML files live"
    )

    subparsers = parser.add_subparsers(dest='workflow_command', help='Workflow commands')
    subparsers.required = True

    # List command
    list_parser = subparsers.add_parser('list', help='List available workflows')

    # Run command parser
    run_parser = subparsers.add_parser('run', help='Run a workflow')
    run_parser.add_argument('workflow_name', nargs='?', default=None, help='Name of the workflow to run')
    run_parser.add_argument('--info', action='store_true', help='Show workflow info')
    run_parser.add_argument('--dry-run', action='store_true', help='Show execution plan only')
    run_parser.add_argument('--output', '-o', help='Write output to file')
    run_parser.add_argument('--json-output', action='store_true', help='Output results as JSON')

    # Parse known args to find the workflow and add its params
    args, remaining_argv = parser.parse_known_args(argv)

    # Configure logging
    configure_console_logging(verbose=args.verbose)

    # If 'run' command, load workflow and add its arguments
    if args.workflow_command == 'run' and args.workflow_name:
        try:
            workflow_path = Path(args.workflows_dir) / f"{args.workflow_name}.yaml"
            if workflow_path.is_file():
                spec = load_workflow(workflow_path)
                for workflow_input in spec.inputs:
                    add_workflow_input_argument(run_parser, workflow_input)
            else:
                if not any(h in remaining_argv for h in ['-h', '--help']):
                     print(f"Error: Workflow '{args.workflow_name}' not found at: {workflow_path}", file=sys.stderr)
                     sys.exit(1)

        except WorkflowValidationError as e:
            print(f"Error validating workflow '{args.workflow_name}': {e}", file=sys.stderr)
            sys.exit(1)

    # Re-parse all arguments now that the parser is fully configured
    # Pass the original argv so that it can be parsed correctly from the start
    args = parser.parse_args(argv)

    # Execute command
    if args.workflow_command == "list":
        list_workflows_command(args.workflows_dir)
        sys.exit(0)
    elif args.workflow_command == "run":
        if not args.workflow_name:
            run_parser.print_help()
            sys.exit(1)
        if args.info:
            show_workflow_info(args.workflows_dir, args.workflow_name)
            sys.exit(0)
        else:
            run_workflow_command(args)
            sys.exit(0)
    else:
        parser.print_help()
        sys.exit(1)


def run_prompt_interface():
    """Handle legacy prompt interface (backward compatibility)."""
    # First pass: get prompt name and check for info request
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument(
        "prompt", help="Name of the prompt (yaml file without .yaml)"
    )
    pre_parser.add_argument(
        "--prompts-dir",
        default=Config.DEFAULT_PROMPTS_DIR,
        help="Directory where prompt YAML files live",
    )
    pre_parser.add_argument(
        "--info",
        action="store_true",
        help="Show detailed information about the prompt and its parameters",
    )
    pre_parser.add_argument(
        "--chat",
        action="store_true",
        help="Launch interactive chat interface",
    )
    pre_parser.add_argument(
        "--list-conversations",
        action="store_true",
        help="List all conversations and exit",
    )
    pre_parser.add_argument(
        "--delete-conversation",
        metavar="ID",
        help="Delete a specific conversation and exit",
    )
    pre_parser.add_argument(
        "--show-conversation",
        metavar="ID",
        help="Show messages from a specific conversation and exit",
    )
    pre_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging output"
    )
    pre_args, remaining_argv = pre_parser.parse_known_args()

    # Configure logging based on verbose setting
    configure_console_logging(verbose=pre_args.verbose)

    logger.debug(f"CLI started with prompt: {pre_args.prompt}")
    logger.debug(f"Verbose mode: {pre_args.verbose}")
    logger.debug(f"Prompts directory: {pre_args.prompts_dir}")

    # Handle conversation management commands
    if pre_args.list_conversations:
        list_conversations_command(pre_args.prompts_dir)
        return

    if pre_args.delete_conversation:
        delete_conversation_command(pre_args.delete_conversation)
        return

    if pre_args.show_conversation:
        show_conversation_command(pre_args.show_conversation)
        return

    # If --chat requested, launch interactive interface
    if pre_args.chat:
        logger.debug("Launching interactive chat interface")
        # Parse remaining args for Orac configuration
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--model-name", help="Override model_name for the LLM")
        parser.add_argument("--api-key", help="Override API key for LLM")
        parser.add_argument(
            "--provider",
            choices=["openai", "google", "anthropic", "azure", "openrouter", "custom"],
            help="Select LLM provider",
        )
        parser.add_argument("--base-url", help="Custom base URL")
        parser.add_argument("--generation-config", help="JSON string for generation_config")
        parser.add_argument("--conversation-id", help="Specify conversation ID")

        args, _ = parser.parse_known_args(remaining_argv)

        # Parse generation config if provided
        gen_config = None
        if args.generation_config:
            try:
                gen_config = json.loads(args.generation_config)
            except Exception as e:
                print(f"Error: generation_config is not valid JSON: {e}", file=sys.stderr)
                sys.exit(1)

        # Launch chat interface
        start_chat_interface(
            prompt_name=pre_args.prompt,
            prompts_dir=pre_args.prompts_dir,
            conversation_id=args.conversation_id,
            model_name=args.model_name,
            api_key=args.api_key,
            provider=args.provider,
            base_url=args.base_url,
            generation_config=gen_config,
            verbose=pre_args.verbose,
        )
        return

    # If --info requested, show info and exit
    if pre_args.info:
        logger.debug("Info mode requested")
        show_prompt_info(pre_args.prompts_dir, pre_args.prompt)
        return

    spec = load_prompt_spec(pre_args.prompts_dir, pre_args.prompt)
    params_spec = spec.get("parameters", [])

    parser = argparse.ArgumentParser(
        prog=os.path.basename(sys.argv[0]),
        description=spec.get("description", f"Run prompt '{pre_args.prompt}'"),
        parents=[pre_parser],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Global overrides
    parser.add_argument("--model-name", help="Override model_name for the LLM")
    parser.add_argument("--api-key", help="Override API key for LLM")
    parser.add_argument(
        "--provider",
        choices=["openai", "google", "anthropic", "azure", "openrouter", "custom"],
        help="Select LLM provider (openai|google|anthropic|azure|openrouter|custom)",
    )
    parser.add_argument(
        "--base-url", help="Custom base URL for CUSTOM provider or to override default"
    )
    parser.add_argument("--generation-config", help="JSON string for generation_config")
    parser.add_argument(
        "--file",
        action="append",
        dest="files",
        help="Add file(s) to the request (can be used multiple times)",
    )
    # Remote file URLs
    parser.add_argument(
        "--file-url",
        action="append",
        dest="file_urls",
        help="Download remote file(s) via URL (can be used multiple times)",
    )
    parser.add_argument(
        "--output", "-o", help="Write output to specified file instead of stdout"
    )
    # Structured JSON output
    parser.add_argument(
        "--json-output",
        action="store_true",
        help="Request strict JSON output (sets response_mime_type=application/json)",
    )
    parser.add_argument(
        "--response-schema",
        metavar="FILE",
        help="Path to JSON schema file for response_schema (OpenAPI style)",
    )
    # Conversation mode flags
    parser.add_argument(
        "--conversation-id",
        help="Specify conversation ID (auto-generated if not provided)",
    )
    parser.add_argument(
        "--reset-conversation",
        action="store_true",
        help="Reset conversation before starting",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save messages to conversation history",
    )

    # Add parameters from the prompt spec with enhanced type support
    for param in params_spec:
        add_parameter_argument(parser, param)

    # Add usage examples to help
    if params_spec:
        examples = ["\nExamples:"]
        examples.append(
            f"  python cli.py {pre_args.prompt} --info  # Show parameter details"
        )
        examples.append(
            f"  python cli.py {pre_args.prompt} --chat  # Interactive chat mode"
        )

        # Basic example
        required_params = [
            p for p in params_spec if p.get("required", "default" not in p)
        ]
        if required_params:
            basic_args = []
            for param in required_params[:2]:  # Show first 2 required params
                arg_name = f"--{param['name'].replace('_', '-')}"
                basic_args.append(f"{arg_name} example")
            examples.append(f"  python cli.py {pre_args.prompt} {' '.join(basic_args)}")

        parser.epilog = "\n".join(examples)

    args = parser.parse_args()

    logger.debug(f"Parsed arguments: {vars(args)}")

    # Parse JSON overrides
    def _safe_json(label: str, s: str):
        try:
            return json.loads(s)
        except Exception as e:
            logger.error(f"{label} JSON parse error: {e}")
            print(f"Error: {label} is not valid JSON: {e}", file=sys.stderr)
            sys.exit(1)

    gen_config = (
        _safe_json("generation_config", args.generation_config)
        if args.generation_config
        else {}
    )

    # Structured output injection
    if args.json_output:
        gen_config = gen_config or {}
        gen_config["response_mime_type"] = "application/json"

    if args.response_schema:
        try:
            with open(args.response_schema, "r", encoding="utf-8") as f:
                schema_json = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read schema file '{args.response_schema}': {e}")
            print(f"Error reading schema file: {e}", file=sys.stderr)
            sys.exit(1)
        gen_config = gen_config or {}
        gen_config["response_schema"] = schema_json

    # Collect and convert parameter values
    param_values = {}
    for param in params_spec:
        name = param["name"]
        cli_value = getattr(args, name)
        param_type = param.get("type", "string")

        if cli_value is not None:
            # Convert CLI string to appropriate type
            converted_value = convert_cli_value(cli_value, param_type, name)
            param_values[name] = converted_value

    logger.debug(f"Final parameter values: {param_values}")

    # Instantiate wrapper and call
    try:
        logger.debug("Creating Orac instance")
        wrapper = Orac(
            prompt_name=args.prompt,
            prompts_dir=args.prompts_dir,
            model_name=args.model_name,
            api_key=args.api_key,
            generation_config=gen_config or None,
            verbose=args.verbose,
            files=args.files,
            file_urls=args.file_urls,
            provider=args.provider,
            base_url=args.base_url,
            conversation_id=args.conversation_id,
            auto_save=not args.no_save,
        )

        # Reset conversation if requested
        if args.reset_conversation and hasattr(args, 'conversation') and args.conversation:
            wrapper.reset_conversation()
            logger.info("Reset conversation history")

        logger.debug("Calling completion method")
        result = wrapper.completion(**param_values)

        # Output result to file or stdout
        if args.output:
            try:
                with open(args.output, "w", encoding="utf-8") as f:
                    f.write(result)
                logger.info(f"Output written to file: {args.output}")
            except IOError as e:
                logger.error(f"Error writing to output file '{args.output}': {e}")
                print(
                    f"Error writing to output file '{args.output}': {e}",
                    file=sys.stderr,
                )
                sys.exit(1)
        else:
            # Output only the result (no additional formatting)
            print(result)

        logger.info("Successfully completed prompt execution")

    except Exception as e:
        logger.error(f"Error running prompt: {e}")
        # Always show critical errors to user, regardless of verbose mode
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
