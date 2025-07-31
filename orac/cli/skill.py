#!/usr/bin/env python3

import argparse
import sys
import json
from loguru import logger
from pathlib import Path

from orac.config import Config
from orac.skill import load_skill, Skill, list_skills, SkillValidationError, SkillExecutionError
from orac.cli_progress import create_cli_reporter
from .utils import add_parameter_argument, convert_cli_value


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


def add_common_skill_args(parser):
    """Add common arguments for skill commands."""
    parser.add_argument(
        '--skills-dir',
        default=Config.DEFAULT_SKILLS_DIR,
        help='Directory where skill YAML files live'
    )


def add_skill_execution_args(parser):
    """Add execution-specific arguments for skills."""
    parser.add_argument('--output', '-o', help='Write output to file')
    parser.add_argument('--json-output', action='store_true', help='Format final output as JSON')


def handle_skill_commands(args, remaining):
    """Handle skill resource commands."""
    if args.action == 'run':
        execute_skill(args, remaining)
    elif args.action == 'list':
        list_skills_command(args.skills_dir)
    elif args.action == 'show':
        show_skill_info(args.skills_dir, args.name)
    elif args.action == 'validate':
        validate_skill_command(args.skills_dir, args.name)
    else:
        print(f"Unknown skill action: {args.action}", file=sys.stderr)
        sys.exit(1)


def execute_skill(args, remaining_args):
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
        # Parse remaining args - ignore unknown args from global scope
        skill_args, unknown = skill_parser.parse_known_args(remaining_args)
        # Create progress reporter if not quiet
        progress_callback = None
        if not args.quiet:
            reporter = create_cli_reporter(verbose=args.verbose, quiet=args.quiet)
            progress_callback = reporter.report
        engine = Skill(spec, skills_dir=args.skills_dir, progress_callback=progress_callback)
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