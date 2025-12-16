"""
CLI commands for chat.

Handles interactive conversations and message management.
"""

import argparse
import sys
from datetime import datetime
from typing import Any

from loguru import logger

from orac.config import Config
from orac.chat import start_chat_interface
from orac.cli_progress import create_cli_reporter

from .base import ResourceCommand
from .errors import show_missing_action_help
from .parsing import safe_json_parse


def add_chat_args(parser: argparse.ArgumentParser) -> None:
    """Add chat-specific arguments."""
    parser.add_argument("--reset-conversation", action="store_true", help="Reset conversation before sending")
    parser.add_argument("--no-save", action="store_true", help="Don't save message to conversation history")
    parser.add_argument("--model-name", help="Override model_name")
    parser.add_argument("--api-key", help="Override API key")
    parser.add_argument(
        "--provider",
        choices=["openai", "google", "anthropic", "azure", "openrouter", "z.ai", "cli", "custom"],
        help="Select LLM provider",
    )
    parser.add_argument("--base-url", help="Custom base URL")
    parser.add_argument("--generation-config", help="JSON string for generation_config")


class ChatCommand(ResourceCommand):
    """CLI command handler for chat."""

    name = "chat"
    help_text = "Interactive conversations"
    description = "Manage interactive conversations"

    actions = {
        "send": {
            "help": "Send a message",
            "args": ["message"],
            "handler": "send",
        },
        "list": {
            "help": "List all conversations",
            "handler": "list",
        },
        "show": {
            "help": "Show conversation history",
            "args": ["conversation_id"],
            "handler": "show",
        },
        "delete": {
            "help": "Delete conversation",
            "args": ["conversation_id"],
            "handler": "delete",
        },
        "interactive": {
            "help": "Start interactive curses-based chat",
            "handler": "interactive",
        },
    }

    examples = {
        "send": "orac chat send 'What is machine learning?'",
        "list": "orac chat list",
        "interactive": "orac chat interactive",
    }

    def setup_parser(self, subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
        """Set up the chat parser with custom arguments."""
        self.parser = subparsers.add_parser(
            self.name,
            help=self.help_text,
            description=self.description,
        )

        action_subparsers = self.parser.add_subparsers(
            dest="action",
            help="Available actions",
            metavar="<action>",
        )

        # send action
        send_parser = action_subparsers.add_parser("send", help="Send a message")
        send_parser.add_argument("message", help="Message to send")
        send_parser.add_argument("--conversation-id", help="Use specific conversation")
        add_chat_args(send_parser)

        # list action
        action_subparsers.add_parser("list", help="List all conversations")

        # show action
        show_parser = action_subparsers.add_parser("show", help="Show conversation history")
        show_parser.add_argument("conversation_id", help="Conversation ID to show")

        # delete action
        delete_parser = action_subparsers.add_parser("delete", help="Delete conversation")
        delete_parser.add_argument("conversation_id", help="Conversation ID to delete")

        # interactive action
        interactive_parser = action_subparsers.add_parser("interactive", help="Start interactive curses-based chat")
        interactive_parser.add_argument("--conversation-id", help="Use specific conversation")
        interactive_parser.add_argument("--prompt-name", default="chat", help="Prompt to use for chat (default: chat)")
        add_chat_args(interactive_parser)

        return self.parser

    def handle_send(self, args: argparse.Namespace, remaining: list[str]) -> None:
        """Send a chat message."""
        gen_config = None
        if getattr(args, "generation_config", None):
            gen_config = safe_json_parse("generation_config", args.generation_config)

        try:
            from orac.prompt import Prompt

            progress_callback = None
            if not args.quiet:
                reporter = create_cli_reporter(verbose=args.verbose, quiet=args.quiet)
                progress_callback = reporter.report

            wrapper = Prompt(
                prompt_name="chat",
                model_name=getattr(args, "model_name", None),
                provider=getattr(args, "provider", None),
                generation_config=gen_config,
                conversation_id=getattr(args, "conversation_id", None),
                auto_save=not getattr(args, "no_save", False),
                progress_callback=progress_callback,
            )

            if getattr(args, "reset_conversation", False):
                wrapper.reset_conversation()
                logger.info("Reset conversation history")

            result = wrapper.completion(
                message=args.message,
                api_key=getattr(args, "api_key", None),
                base_url=getattr(args, "base_url", None),
            )

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

    def handle_list(self, args: argparse.Namespace, remaining: list[str]) -> None:
        """List all conversations in the database."""
        from orac.conversation_db import ConversationDB

        db = ConversationDB(Config.get_conversation_db_path())
        conversations = db.list_conversations()

        if not conversations:
            print("No conversations found.")
            return

        print(f"\nConversations ({len(conversations)} total):")
        print("-" * 80)
        print(f"{'ID':36} {'Prompt':15} {'Messages':8} {'Updated':20}")
        print("-" * 80)

        for conv in conversations:
            try:
                dt = datetime.fromisoformat(conv["updated_at"].replace("Z", "+00:00"))
                updated = dt.strftime("%Y-%m-%d %H:%M:%S")
            except:
                updated = conv["updated_at"][:19]

            print(f"{conv['id']:36} {conv['prompt_name']:15} {conv['message_count']:8} {updated:20}")

    def handle_show(self, args: argparse.Namespace, remaining: list[str]) -> None:
        """Show messages from a specific conversation."""
        from orac.conversation_db import ConversationDB

        db = ConversationDB(Config.get_conversation_db_path())
        messages = db.get_messages(args.conversation_id)

        if not messages:
            print(f"No messages found for conversation: {args.conversation_id}")
            return

        print(f"\nConversation: {args.conversation_id}")
        print("-" * 80)
        for msg in messages:
            role_label = "User" if msg["role"] == "user" else "Assistant"
            print(f"[{msg['timestamp']}] {role_label}:\n{msg['content']}\n")

    def handle_delete(self, args: argparse.Namespace, remaining: list[str]) -> None:
        """Delete a specific conversation."""
        from orac.conversation_db import ConversationDB

        db = ConversationDB(Config.get_conversation_db_path())
        if db.conversation_exists(args.conversation_id):
            db.delete_conversation(args.conversation_id)
            print(f"Deleted conversation: {args.conversation_id}")
        else:
            print(f"Conversation not found: {args.conversation_id}")

    def handle_interactive(self, args: argparse.Namespace, remaining: list[str]) -> None:
        """Start interactive curses-based chat interface."""
        gen_config = None
        if getattr(args, "generation_config", None):
            gen_config = safe_json_parse("generation_config", args.generation_config)

        try:
            prompt_kwargs = {
                "model_name": getattr(args, "model_name", None),
                "provider": getattr(args, "provider", None),
                "generation_config": gen_config,
                "auto_save": not getattr(args, "no_save", False),
            }

            # Remove None values
            prompt_kwargs = {k: v for k, v in prompt_kwargs.items() if v is not None}

            start_chat_interface(
                prompt_name=getattr(args, "prompt_name", "chat"),
                conversation_id=getattr(args, "conversation_id", None),
                **prompt_kwargs,
            )

        except Exception as e:
            logger.error(f"Error starting interactive chat: {e}")
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


# Module-level instance for backwards compatibility
_chat_command = ChatCommand()


def add_chat_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    """Add chat resource parser (for backwards compatibility)."""
    return _chat_command.setup_parser(subparsers)


def handle_chat_commands(args: argparse.Namespace, remaining: list[str]) -> None:
    """Handle chat resource commands (for backwards compatibility)."""
    _chat_command.handle(args, remaining)
