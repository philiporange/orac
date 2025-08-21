#!/usr/bin/env python3

import argparse
import sys
import json
from loguru import logger
from pathlib import Path

from orac.config import Config
from orac.prompt import Prompt
from orac.cli_progress import create_cli_reporter
from .utils import load_prompt_spec, convert_cli_value, add_parameter_argument, safe_json_parse


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


def add_common_prompt_args(parser):
    """Add common arguments for prompt commands."""
    parser.add_argument(
        '--prompts-dir',
        default=str(Config.get_prompts_dir()),
        help='Directory where prompt YAML files live'
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


def handle_prompt_commands(args, remaining):
    """Handle prompt resource commands."""
    if args.action == 'run':
        execute_prompt(args, remaining)
    elif args.action == 'list':
        list_prompts_command(args.prompts_dir)
    elif args.action == 'show':
        show_prompt_info(args.prompts_dir, args.name)
    elif args.action == 'validate':
        validate_prompt_command(args.prompts_dir, args.name)
    else:
        print(f"Unknown prompt action: {args.action}", file=sys.stderr)
        sys.exit(1)


def execute_prompt(args, remaining_args):
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
    
    # Parse remaining args to get parameter values - ignore unknown args from global scope
    prompt_args, unknown = prompt_parser.parse_known_args(remaining_args)
    
    # Parse JSON overrides
    gen_config = (
        safe_json_parse("generation_config", prompt_args.generation_config)
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

    # Create Prompt instance and execute
    try:
        logger.debug("Creating Prompt instance")
        
        # Create progress reporter if not quiet
        progress_callback = None
        if not args.quiet:
            reporter = create_cli_reporter(verbose=args.verbose, quiet=args.quiet)
            progress_callback = reporter.report
        
        wrapper = Prompt(
            prompt_name=args.name,
            prompts_dir=args.prompts_dir,
            model_name=args.model_name,
            generation_config=gen_config or None,
            verbose=args.verbose,
            files=getattr(prompt_args, 'files', None),
            file_urls=getattr(prompt_args, 'file_urls', None),
            provider=args.provider,
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


def list_prompts_command(prompts_dir: str):
    """List available prompts."""
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