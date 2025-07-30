#!/usr/bin/env python3

import argparse
import sys
import json
from datetime import datetime
from loguru import logger

from orac.config import Config
from orac.chat import start_chat_interface
from orac.cli_progress import create_cli_reporter
from .utils import safe_json_parse


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


def handle_chat_commands(args, remaining):
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


def handle_chat_interactive(args):
    """Start interactive curses-based chat interface."""
    # Parse generation config if provided
    gen_config = None
    if getattr(args, 'generation_config', None):
        gen_config = safe_json_parse("generation_config", args.generation_config)
    
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
        gen_config = safe_json_parse("generation_config", args.generation_config)
    
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