#!/usr/bin/env python3
"""
Interactive chat interface for Orac using curses.
Provides a beautiful terminal UI for conversations.
"""

import curses
import textwrap
import sys
import threading
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from orac.prompt import Prompt
from orac.conversation_db import ConversationDB
from orac.config import Config
from loguru import logger


class MessageRole(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class ChatMessage:
    role: MessageRole
    content: str
    timestamp: datetime
    loading: bool = False

    @classmethod
    def from_db(cls, db_msg: Dict[str, Any]) -> 'ChatMessage':
        """Create ChatMessage from database message dict."""
        return cls(
            role=MessageRole.USER if db_msg['role'] == 'user' else MessageRole.ASSISTANT,
            content=db_msg['content'],
            timestamp=datetime.fromisoformat(db_msg['timestamp'].replace(' ', 'T'))
        )


class ChatInterface:
    """Interactive chat interface using curses."""

    def __init__(self, prompt_instance: Prompt, conversation_id: Optional[str] = None):
        self.orac = prompt_instance
        self.conversation_id = conversation_id or self.orac.conversation_id
        self.messages: List[ChatMessage] = []
        self.input_buffer = ""
        self.scroll_offset = 0
        self.input_history: List[str] = []
        self.input_history_index = 0

        # UI State
        self.dirty = True  # Flag to indicate if a redraw is needed

        # Loading animation state
        self.is_loading = False
        self.loading_thread: Optional[threading.Thread] = None
        self.animation_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.animation_index = 0

        # UI configuration
        self.input_height = 3
        self.status_height = 1
        self.padding = 1

        # Colors will be initialized in setup_colors
        self.colors = {}

    def setup_colors(self):
        """Initialize color pairs for the interface."""
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)
        curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_WHITE)
        curses.init_pair(6, curses.COLOR_RED, -1)
        curses.init_pair(7, curses.COLOR_MAGENTA, -1)
        self.colors = {
            'user': curses.color_pair(1), 'assistant': curses.color_pair(2),
            'timestamp': curses.color_pair(3), 'status': curses.color_pair(4),
            'input': curses.color_pair(5), 'error': curses.color_pair(6),
            'system': curses.color_pair(7),
        }

    def load_conversation_history(self):
        """Load existing conversation history."""
        if self.orac.use_conversation:
            history = self.orac.get_conversation_history()
            for msg in history:
                self.messages.append(ChatMessage.from_db(msg))
        self.scroll_offset = float('inf')
        self.dirty = True

    def wrap_text(self, text: str, width: int) -> List[str]:
        lines = []
        for paragraph in text.split('\n'):
            if paragraph:
                lines.extend(textwrap.wrap(paragraph, width=width))
            else:
                lines.append('')
        return lines

    def draw_message(self, win, y: int, x: int, message: ChatMessage, width: int, line_offset: int = 0) -> int:
        try:
            timestamp_str = message.timestamp.strftime("%H:%M")
            role_str = " You: " if message.role == MessageRole.USER else " Assistant: "
            role_color = self.colors['user'] if message.role == MessageRole.USER else self.colors['assistant']
            if message.role == MessageRole.SYSTEM: role_color = self.colors['error']

            if message.loading:
                win.addstr(y, x, timestamp_str, self.colors['timestamp'])
                win.addstr(y, x + len(timestamp_str), role_str, role_color | curses.A_BOLD)
                animation_char = self.animation_chars[self.animation_index]
                loading_text = f" {animation_char} Thinking..."
                win.addstr(y, x + len(timestamp_str) + len(role_str), loading_text, role_color)
                return 1

            indent = len(timestamp_str) + len(role_str)
            wrap_width = max(1, width - indent - x - 2)
            wrapped_lines = self.wrap_text(message.content, wrap_width)
            if not wrapped_lines: wrapped_lines = ['']

            current_y = y
            for i in range(line_offset, len(wrapped_lines)):
                if current_y >= win.getmaxyx()[0] - 1: break
                line_content = wrapped_lines[i]
                if i == 0:
                    win.addstr(current_y, x, timestamp_str, self.colors['timestamp'])
                    win.addstr(current_y, x + len(timestamp_str), role_str, role_color | curses.A_BOLD)
                    win.addstr(current_y, x + indent, line_content, role_color)
                else:
                    win.addstr(current_y, x + indent, line_content, role_color)
                current_y += 1
            return len(wrapped_lines)
        except curses.error:
            return 1

    def draw_messages(self, win):
        win.erase()
        height, width = win.getmaxyx()
        y, visible_height = 1, height - 2

        message_lines = []
        for msg in self.messages:
            lines_needed = 1 if msg.loading else len(self.wrap_text(msg.content, max(1, width - (5 + 10) - 2 - 2)))
            message_lines.append(max(1, lines_needed))

        total_lines = sum(message_lines) + len(self.messages) - 1
        max_scroll = max(0, total_lines - visible_height)
        self.scroll_offset = min(self.scroll_offset, max_scroll)
        if self.scroll_offset < 0: self.scroll_offset = 0

        current_line = 0
        for i, msg in enumerate(self.messages):
            lines_for_this_message = message_lines[i]
            screen_y, line_offset = y + current_line - self.scroll_offset, 0
            if screen_y < y:
                line_offset = y - screen_y
                screen_y = y
            if screen_y < height - 1 and line_offset < lines_for_this_message:
                self.draw_message(win, screen_y, 2, msg, width, line_offset)
            current_line += lines_for_this_message + 1

    def draw_input_area(self, win):
        win.erase()
        height, width = win.getmaxyx()
        if width < 4: return
        try:
            prompt = ">>> "
            win.addstr(1, 1, prompt, self.colors['input'] | curses.A_BOLD)
            input_start, max_input_width = len(prompt) + 1, width - len(prompt) - 3
            display_text = self.input_buffer[-(max_input_width):] if len(self.input_buffer) > max_input_width else self.input_buffer
            win.addstr(1, input_start, display_text, self.colors['input'])
            cursor_x = input_start + len(display_text)
            if cursor_x < width - 2:
                win.move(1, cursor_x)
        except curses.error: pass

    def draw_status_bar(self, win):
        win.erase()
        height, width = win.getmaxyx()
        if width <= 1: return
        try:
            win.bkgd(' ', self.colors['status'])
            status_left = f" Orac Chat | {self.orac.prompt_name} | Messages: {len(self.messages)} "
            status_right = " Ctrl-K: Clear | Ctrl-C: Exit | ↑↓: Scroll "
            win.addstr(0, 0, status_left[:width - 1], self.colors['status'])
            if len(status_right) + 2 < width and len(status_left) + len(status_right) + 2 < width:
                win.addstr(0, width - len(status_right) - 1, status_right, self.colors['status'])
        except curses.error: pass

    def draw_interface(self, stdscr):
        try:
            height, width = stdscr.getmaxyx()
            
            # Ensure minimum dimensions
            if height < 5 or width < 10:
                return
                
            chat_height = height - self.input_height - self.status_height
            if chat_height < 1: 
                chat_height = 1

            # Create windows
            status_win = curses.newwin(self.status_height, width, 0, 0)
            chat_win = curses.newwin(chat_height, width, self.status_height, 0)
            input_win = curses.newwin(self.input_height, width, height - self.input_height, 0)

            # Draw all components
            self.draw_status_bar(status_win)
            self.draw_messages(chat_win)
            chat_win.box()
            self.draw_input_area(input_win)
            input_win.box()

            # Refresh all windows
            status_win.noutrefresh()
            chat_win.noutrefresh()
            input_win.noutrefresh()
            curses.doupdate()
            
        except curses.error:
            pass

    def send_message(self):
        if not self.input_buffer.strip() or self.is_loading: return
        self.input_history.append(self.input_buffer)
        self.input_history_index = len(self.input_history)
        user_msg = ChatMessage(role=MessageRole.USER, content=self.input_buffer.strip(), timestamp=datetime.now())
        self.messages.append(user_msg)
        message_text, self.input_buffer = self.input_buffer.strip(), ""
        assistant_msg = ChatMessage(role=MessageRole.ASSISTANT, content="", timestamp=datetime.now(), loading=True)
        self.messages.append(assistant_msg)
        self.scroll_offset = float('inf')
        self.is_loading = True
        self.dirty = True
        self.loading_thread = threading.Thread(target=self._get_assistant_response, args=(message_text, assistant_msg))
        self.loading_thread.start()

    def _get_assistant_response(self, message_text: str, placeholder_msg: ChatMessage):
        try:
            params = self.orac._resolve_parameters()
            if 'message' in params or any(p['name'] == 'message' for p in self.orac.parameters_spec):
                response = self.orac.completion(message=message_text)
            else:
                response = self.orac.completion(**{self.orac.parameters_spec[0]['name']: message_text})
            placeholder_msg.content = response
            placeholder_msg.role = MessageRole.ASSISTANT
        except Exception as e:
            placeholder_msg.content = f"Error: {str(e)}"
            placeholder_msg.role = MessageRole.SYSTEM
        finally:
            placeholder_msg.loading = False
            placeholder_msg.timestamp = datetime.now()
            self.is_loading = False
            self.scroll_offset = float('inf')
            self.dirty = True

    def clear_history(self):
        self.messages = []
        self.scroll_offset = 0
        if self.orac.use_conversation: self.orac.reset_conversation()
        self.dirty = True

    def handle_input(self, ch):
        if self.is_loading:
            if ch in {curses.KEY_UP, curses.KEY_DOWN, curses.KEY_PPAGE, curses.KEY_NPAGE, 11}:
                if ch == curses.KEY_UP: self.scroll_offset = max(0, self.scroll_offset - 1)
                elif ch == curses.KEY_DOWN: self.scroll_offset += 1
                elif ch == curses.KEY_PPAGE: self.scroll_offset = max(0, self.scroll_offset - 10)
                elif ch == curses.KEY_NPAGE: self.scroll_offset += 10
                elif ch == 11: self.clear_history()
                self.dirty = True
            return

        if ch in {ord('\n'), curses.KEY_ENTER}: self.send_message()
        elif ch in {curses.KEY_BACKSPACE, 127}: self.input_buffer = self.input_buffer[:-1]
        elif ch == 11: self.clear_history()
        elif ch == curses.KEY_UP: self.scroll_offset = max(0, self.scroll_offset - 1)
        elif ch == curses.KEY_DOWN: self.scroll_offset += 1
        elif ch == curses.KEY_PPAGE: self.scroll_offset = max(0, self.scroll_offset - 10)
        elif ch == curses.KEY_NPAGE: self.scroll_offset += 10
        elif 32 <= ch <= 126: self.input_buffer += chr(ch)
        self.dirty = True

    def run(self, stdscr):
        self.setup_colors()
        self.load_conversation_history()
        
        # Set up curses properly
        stdscr.keypad(True)
        stdscr.clear()
        stdscr.refresh()  # Ensure initial clear is flushed
        
        # Force initial render with dirty flag
        curses.curs_set(1)
        self.dirty = True

        while True:
            if self.dirty:
                if self.is_loading:
                    curses.curs_set(0)  # Hide cursor
                else:
                    curses.curs_set(1)  # Show cursor
                self.draw_interface(stdscr)
                self.dirty = False

            stdscr.timeout(100 if self.is_loading else -1)

            try:
                ch = stdscr.getch()
            except KeyboardInterrupt:
                break

            if ch == curses.KEY_RESIZE:
                self.dirty = True
                continue
            
            if ch != curses.ERR:
                if ch == 3: break
                self.handle_input(ch)
            
            if self.is_loading:
                self.animation_index = (self.animation_index + 1) % len(self.animation_chars)
                self.dirty = True

        curses.curs_set(1)

def start_chat_interface(prompt_name: str, prompts_dir: Optional[str] = None, conversation_id: Optional[str] = None, **prompt_kwargs):
    try:
        prompt = Prompt(prompt_name=prompt_name, prompts_dir=prompts_dir, use_conversation=True, conversation_id=conversation_id, **prompt_kwargs)
        chat = ChatInterface(prompt, conversation_id)
        curses.wrapper(chat.run)
    except Exception as e:
        logger.error(f"Error in chat interface: {e}")
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    start_chat_interface("chat")