#!/usr/bin/env python3

import argparse
import sys
import json
from loguru import logger
from pathlib import Path

from orac.config import Config
from orac.flow import load_flow, Flow, list_flows, FlowValidationError, FlowExecutionError
from orac.cli_progress import create_cli_reporter
from .utils import add_flow_input_argument, convert_cli_value


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


def add_flow_execution_args(parser):
    """Add execution-specific arguments for flows."""
    parser.add_argument('--dry-run', action='store_true', help='Show execution plan without running')
    parser.add_argument('--output', '-o', help='Write output to file')
    parser.add_argument('--json-output', action='store_true', help='Format final output as JSON')


def handle_flow_commands(args, remaining):
    """Handle flow resource commands."""
    if args.action == 'run':
        execute_flow(args, remaining)
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


def execute_flow(args, remaining_args):
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
        
        # Parse remaining args - ignore unknown args from global scope  
        flow_args, unknown = flow_parser.parse_known_args(remaining_args)
        
        # Create progress reporter if not quiet
        progress_callback = None
        if not args.quiet:
            reporter = create_cli_reporter(verbose=args.verbose, quiet=args.quiet)
            progress_callback = reporter.report
        
        engine = Flow(spec, prompts_dir=args.prompts_dir, progress_callback=progress_callback)
        
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


def show_flow_graph(flows_dir: str, flow_name: str):
    """Show dependency graph for a flow."""
    flow_path = Path(flows_dir) / f"{flow_name}.yaml"
    
    try:
        spec = load_flow(flow_path)
        engine = Flow(spec, prompts_dir=Config.DEFAULT_PROMPTS_DIR)
        
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
        engine = Flow(spec, prompts_dir=Config.DEFAULT_PROMPTS_DIR)
        
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