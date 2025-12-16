#!/usr/bin/env python3
"""
Create command for generating new orac resources using Claude Opus 4.5.

This command uses the full codebase context to help users create new prompts,
flows, agents, skills, etc. and saves them to their .orac directory.
"""

import argparse
import subprocess
import sys
import os
from pathlib import Path

from orac.config import Config, Provider


def add_create_parser(subparsers):
    """Add create resource parser."""
    create_parser = subparsers.add_parser(
        'create',
        help='Create new prompts, flows, agents using AI',
        description='''
Create new orac resources (prompts, flows, agents, skills) using Claude Opus 4.5.

This command provides the full orac codebase as context, allowing the AI to
understand the framework and create well-structured resources that follow
existing patterns.

Examples:
  orac create prompt "A prompt that summarizes technical documents"
  orac create flow "A research flow that searches, summarizes, and reports"
  orac create agent "An agent that helps with code review"
  orac create skill "A skill that validates JSON schemas"
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    create_parser.add_argument(
        'resource_type',
        choices=['prompt', 'flow', 'agent', 'skill'],
        help='Type of resource to create'
    )
    create_parser.add_argument(
        'description',
        help='Description of what you want to create'
    )
    create_parser.add_argument(
        '--name',
        help='Name for the resource (auto-generated if not provided)'
    )
    create_parser.add_argument(
        '--project',
        action='store_true',
        help='Save to project .orac/ instead of user ~/.config/orac/'
    )
    create_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be created without saving'
    )

    return create_parser


def handle_create_commands(args, remaining):
    """Handle create resource commands."""
    create_resource(
        resource_type=args.resource_type,
        description=args.description,
        name=getattr(args, 'name', None),
        project=getattr(args, 'project', False),
        dry_run=getattr(args, 'dry_run', False),
        verbose=getattr(args, 'verbose', False),
    )


def get_codebase_context() -> str:
    """Get the full orac codebase using catenator."""
    try:
        result = subprocess.run(
            ['catenator', '--ignore-tests', str(Config.PROJECT_ROOT)],
            capture_output=True,
            text=True,
            timeout=60
        )
        if result.returncode == 0:
            return result.stdout
        else:
            print(f"Warning: catenator failed: {result.stderr}", file=sys.stderr)
            return ""
    except FileNotFoundError:
        print("Warning: catenator not found, proceeding without codebase context", file=sys.stderr)
        return ""
    except subprocess.TimeoutExpired:
        print("Warning: catenator timed out", file=sys.stderr)
        return ""


def get_example_resources(resource_type: str) -> str:
    """Get example resources of the given type."""
    examples = []

    if resource_type == 'prompt':
        prompts_dir = Config.get_prompts_dir()
        for yaml_file in list(prompts_dir.glob("*.yaml"))[:3]:
            try:
                with open(yaml_file, 'r') as f:
                    examples.append(f"# Example: {yaml_file.name}\n{f.read()}")
            except Exception:
                pass
    elif resource_type == 'flow':
        flows_dir = Config.get_flows_dir()
        for yaml_file in list(flows_dir.glob("*.yaml"))[:2]:
            try:
                with open(yaml_file, 'r') as f:
                    examples.append(f"# Example: {yaml_file.name}\n{f.read()}")
            except Exception:
                pass
    elif resource_type == 'skill':
        skills_dir = Config.get_skills_dir()
        for yaml_file in list(skills_dir.glob("*.yaml"))[:2]:
            try:
                with open(yaml_file, 'r') as f:
                    examples.append(f"# Example: {yaml_file.name}\n{f.read()}")
            except Exception:
                pass
    elif resource_type == 'agent':
        agents_dir = Config.get_agents_dir()
        for yaml_file in list(agents_dir.glob("*.yaml"))[:2]:
            try:
                with open(yaml_file, 'r') as f:
                    examples.append(f"# Example: {yaml_file.name}\n{f.read()}")
            except Exception:
                pass

    return "\n\n".join(examples)


def create_resource(
    resource_type: str,
    description: str,
    name: str = None,
    project: bool = False,
    dry_run: bool = False,
    verbose: bool = False,
):
    """Create a new resource using Claude Opus 4.5 with thinking."""
    import orac
    from orac.auth import AuthManager

    print(f"🔨 Creating new {resource_type}...")
    print(f"   Description: {description}")

    # Get codebase context
    print("   Loading codebase context...")
    codebase = get_codebase_context()

    # Get example resources
    examples = get_example_resources(resource_type)

    # Build the prompt
    system_prompt = f"""You are an expert at creating orac framework resources. You have access to the full orac codebase and understand how to create well-structured {resource_type}s.

Your task is to create a new {resource_type} based on the user's description. Follow the patterns and conventions used in existing orac resources.

IMPORTANT RULES:
1. Output ONLY the YAML content for the {resource_type}, nothing else
2. Do not include markdown code fences or explanations
3. Follow the exact schema used by existing {resource_type}s in the codebase
4. Use meaningful names for parameters and outputs
5. Include helpful descriptions
6. For prompts: use ${{parameter}} syntax for template variables
7. For flows: ensure step dependencies are correct
8. For skills: remember a corresponding .py file is needed (mention this in a comment)
9. For agents: define appropriate tools and system prompts

Here are example {resource_type}s from the codebase:

{examples}
"""

    user_prompt = f"""Create a new {resource_type} with the following requirements:

{description}

{"Suggested name: " + name if name else "Choose an appropriate name for this " + resource_type + "."}

Here is the full orac codebase for reference:

{codebase[:100000] if codebase else "(Codebase context not available)"}

Output ONLY the YAML content, no explanations or markdown."""

    # Initialize client with CLI provider and Opus thinking model
    auth_manager = AuthManager()

    # Check if CLI provider has consent
    if not auth_manager.has_consent(Provider.CLI):
        print("\n🔐 The create command requires the CLI provider (Claude Opus 4.5).")
        if not auth_manager.request_consent(Provider.CLI, interactive=True):
            print("❌ Consent denied. Cannot proceed.", file=sys.stderr)
            sys.exit(1)

    try:
        client = orac.init(
            providers={Provider.CLI: {"from_config": True}},
            default_provider=Provider.CLI
        )
    except Exception as e:
        print(f"❌ Failed to initialize client: {e}", file=sys.stderr)
        sys.exit(1)

    print("   Generating with Claude Opus 4.5 (thinking-high)...")

    try:
        # Call the API with thinking-high model
        result = client.completion(
            prompt=user_prompt,
            system_prompt=system_prompt,
            model_name="claude-opus-4-5-thinking-high",
            provider=Provider.CLI,
        )
    except Exception as e:
        print(f"❌ Generation failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Clean up the result (remove any markdown fences if present)
    yaml_content = result.strip()
    if yaml_content.startswith("```"):
        lines = yaml_content.split("\n")
        # Remove first and last lines if they're fences
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        yaml_content = "\n".join(lines)

    # Determine output path
    if project:
        base_dir = Path.cwd() / ".orac" / f"{resource_type}s"
    else:
        base_dir = Config._USER_CONFIG_DIR / f"{resource_type}s"

    # Extract name from YAML if not provided
    if not name:
        import yaml
        try:
            parsed = yaml.safe_load(yaml_content)
            # Try 'name' field first, then use description to generate a name
            name = parsed.get('name')
            if not name and parsed.get('description'):
                # Generate name from description, removing filler words
                filler_words = {'a', 'an', 'the', 'that', 'which', 'for', 'to', 'of', 'and', 'or', 'with', 'into'}
                desc_words = [w for w in parsed['description'].split() if w.lower() not in filler_words][:4]
                name = '-'.join(desc_words).lower()
            if not name:
                name = f'new-{resource_type}'
        except Exception:
            name = f'new-{resource_type}'

    # Sanitize name for filename
    filename = name.lower().replace(' ', '-').replace('_', '-')
    filename = ''.join(c for c in filename if c.isalnum() or c == '-')
    output_path = base_dir / f"{filename}.yaml"

    print(f"\n{'=' * 60}")
    print(f"Generated {resource_type}:")
    print(f"{'=' * 60}")
    print(yaml_content)
    print(f"{'=' * 60}")

    if dry_run:
        print(f"\n📝 Dry run - would save to: {output_path}")
        return

    # Save the file
    try:
        base_dir.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(yaml_content)
        print(f"\n✅ Saved to: {output_path}")

        # Provide usage hint
        if resource_type == 'prompt':
            print(f"\n💡 Usage: orac prompt run {filename}")
        elif resource_type == 'flow':
            print(f"\n💡 Usage: orac flow run {filename}")
        elif resource_type == 'agent':
            print(f"\n💡 Usage: orac agent run {filename}")
        elif resource_type == 'skill':
            print(f"\n⚠️  Note: Skills require a corresponding .py file with the implementation.")
            print(f"   Create: {base_dir / f'{filename}.py'}")

    except Exception as e:
        print(f"❌ Failed to save: {e}", file=sys.stderr)
        sys.exit(1)
