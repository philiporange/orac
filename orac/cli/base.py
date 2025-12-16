"""
Base class for Orac CLI resource commands.

Provides a declarative framework for defining CLI commands with
consistent error handling, help formatting, and argument parsing.
"""

import argparse
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable, Optional

from .errors import (
    show_missing_action_help,
    show_unknown_action_error,
    show_resource_not_found_error,
    suggest_similar,
)
from .parsing import (
    DynamicArgumentParser,
    add_parameter_to_parser,
    get_param_names,
)


class ResourceCommand(ABC):
    """
    Base class for resource-based CLI commands.

    Subclasses define their resource type and actions declaratively,
    and this base class handles parser setup, routing, and error handling.
    """

    # Override these in subclasses
    name: str = ""  # e.g., "prompt"
    help_text: str = ""  # e.g., "Single AI interactions"
    description: str = ""  # Longer description for help

    # Actions defined as: {action_name: {'help': str, 'args': [positional args]}}
    actions: dict[str, dict[str, Any]] = {}

    # Examples for help text: {action_name: example_command}
    examples: dict[str, str] = {}

    # Common arguments added to the resource parser
    common_args: list[tuple[str, dict]] = []

    def __init__(self):
        """Initialize the resource command."""
        self.parser: Optional[argparse.ArgumentParser] = None
        self.action_parsers: dict[str, argparse.ArgumentParser] = {}

    def setup_parser(self, subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
        """
        Register this resource with the main argument parser.

        Args:
            subparsers: Subparsers from the main parser

        Returns:
            The created resource parser
        """
        self.parser = subparsers.add_parser(
            self.name,
            help=self.help_text,
            description=self.description or self.help_text,
        )

        # Add common arguments
        for arg_name, arg_kwargs in self.common_args:
            self.parser.add_argument(arg_name, **arg_kwargs)

        # Create action subparsers
        action_subparsers = self.parser.add_subparsers(
            dest="action",
            help="Available actions",
            metavar="<action>",
        )

        # Add each action
        for action_name, action_config in self.actions.items():
            action_parser = action_subparsers.add_parser(
                action_name,
                help=action_config.get("help", ""),
            )

            # Add positional arguments
            for pos_arg in action_config.get("args", []):
                action_parser.add_argument(pos_arg, help=f"Name of the {self.name} to {action_name}")

            # Add action-specific arguments
            args_func = action_config.get("add_args")
            if args_func:
                args_func(action_parser)

            self.action_parsers[action_name] = action_parser

        return self.parser

    def handle(self, args: argparse.Namespace, remaining: list[str]) -> None:
        """
        Route to the appropriate action handler.

        Args:
            args: Parsed arguments
            remaining: Remaining unparsed arguments
        """
        if args.action is None:
            self._show_missing_action_help()
            return

        # Check for unknown action
        if args.action not in self.actions:
            show_unknown_action_error(
                self.name,
                args.action,
                list(self.actions.keys()),
            )
            return

        # Get the handler method
        handler_name = self.actions[args.action].get("handler", args.action)
        handler = getattr(self, f"handle_{handler_name}", None)

        if handler is None:
            print(f"Error: Handler for action '{args.action}' not implemented.", file=sys.stderr)
            sys.exit(1)

        handler(args, remaining)

    def _show_missing_action_help(self) -> None:
        """Show help when no action is specified."""
        actions_help = {
            action: config.get("help", "")
            for action, config in self.actions.items()
        }
        show_missing_action_help(self.name, actions_help, self.examples)

    def get_resource_dir(self, args: argparse.Namespace) -> Path:
        """
        Get the directory for this resource type.

        Override this in subclasses to specify how to get the resource directory.
        """
        raise NotImplementedError("Subclass must implement get_resource_dir()")

    def list_available(self, resource_dir: Path) -> list[str]:
        """
        List available resources in the directory.

        Args:
            resource_dir: Directory to search

        Returns:
            List of resource names (without extension)
        """
        if not resource_dir.exists():
            return []

        yaml_files = list(resource_dir.glob("*.yaml")) + list(resource_dir.glob("*.yml"))
        return sorted([f.stem for f in yaml_files])

    def check_resource_exists(
        self,
        name: str,
        resource_dir: Path,
        list_command: Optional[str] = None,
    ) -> Path:
        """
        Check if a resource exists and return its path.

        Args:
            name: Resource name
            resource_dir: Directory to search
            list_command: Command to list resources (for error message)

        Returns:
            Path to the resource file

        Raises:
            SystemExit: If resource not found
        """
        # Check for direct path
        if name.endswith((".yaml", ".yml")) and Path(name).is_file():
            return Path(name)

        # Check in resource directory
        path = resource_dir / f"{name}.yaml"
        if path.exists():
            return path

        # Also try .yml extension
        path_yml = resource_dir / f"{name}.yml"
        if path_yml.exists():
            return path_yml

        # Resource not found - show helpful error
        available = self.list_available(resource_dir)
        list_cmd = list_command or f"orac {self.name} list"

        show_resource_not_found_error(
            self.name.capitalize(),
            name,
            available,
            list_cmd,
        )
        # Never returns - show_resource_not_found_error calls sys.exit


class ListableMixin:
    """Mixin that adds standard list functionality to a resource."""

    def handle_list(self, args: argparse.Namespace, remaining: list[str]) -> None:
        """
        List all available resources.

        Expects: get_resource_dir(), load_spec(), name to be defined.
        """
        resource_dir = self.get_resource_dir(args)

        if not resource_dir.exists():
            print(f"{self.name.capitalize()}s directory not found: {resource_dir}")
            return

        available = self.list_available(resource_dir)

        if not available:
            print(f"No {self.name}s found in {resource_dir}")
            return

        print(f"\nAvailable {self.name}s ({len(available)} total):")
        print("-" * 80)
        print(f"{'Name':20} {'Description':60}")
        print("-" * 80)

        for name in available:
            try:
                spec = self.load_spec_for_list(resource_dir / f"{name}.yaml")
                desc = spec.get("description", "No description available") if isinstance(spec, dict) else getattr(spec, "description", "No description available")
                desc = str(desc)[:57] + "..." if len(str(desc)) > 60 else str(desc)
                print(f"{name:20} {desc:60}")
            except Exception:
                print(f"{name:20} {'(Error loading)':60}")

    def load_spec_for_list(self, path: Path) -> Any:
        """
        Load a spec for listing. Override if needed.

        Args:
            path: Path to the YAML file

        Returns:
            Loaded spec (dict or object with description attribute)
        """
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)


class ShowableMixin:
    """Mixin that adds standard show functionality to a resource."""

    @abstractmethod
    def format_resource_info(self, spec: Any, name: str) -> None:
        """
        Format and print resource info.

        Args:
            spec: The loaded resource spec
            name: Name of the resource
        """
        pass


class ValidatableMixin:
    """Mixin that adds standard validate functionality to a resource."""

    def handle_validate(self, args: argparse.Namespace, remaining: list[str]) -> None:
        """Validate a resource YAML file."""
        resource_dir = self.get_resource_dir(args)
        path = self.check_resource_exists(args.name, resource_dir)

        try:
            spec = self.load_spec_for_validation(path)
            print(f"✓ {self.name.capitalize()} '{args.name}' is valid")
            self.additional_validation(spec, args.name)
            print(f"Validation complete for '{args.name}'")
        except Exception as e:
            print(f"✗ Validation failed for '{args.name}': {e}", file=sys.stderr)
            sys.exit(1)

    def load_spec_for_validation(self, path: Path) -> Any:
        """Load a spec for validation. Override if needed."""
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def additional_validation(self, spec: Any, name: str) -> None:
        """
        Perform additional validation checks.

        Override to add resource-specific validation.
        """
        pass


def create_standard_examples(resource_name: str, run_example_args: str = "") -> dict[str, str]:
    """
    Create standard examples for a resource.

    Args:
        resource_name: Name of the resource type
        run_example_args: Additional args for run example

    Returns:
        Dict of action -> example command
    """
    return {
        "run": f"orac {resource_name} run <name>{run_example_args}",
        "list": f"orac {resource_name} list",
        "show": f"orac {resource_name} show <name>",
    }
