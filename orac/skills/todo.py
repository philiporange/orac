"""
Todo list skill for managing agent/team goals.

Uses a markdown file to store todo items with support for:
- CRUD operations (create, read, update, delete)
- Immutable items (can only be marked complete, not edited/deleted)
- Status tracking (pending/completed)

Markdown format:
```
# Todo List

- [ ] #1 First task
- [ ] #2 Second task [immutable]
- [x] #3 Completed task
```
"""

import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Any, List, Optional


@dataclass
class TodoItem:
    id: int
    description: str
    completed: bool = False
    immutable: bool = False


def execute(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute a todo list operation.

    Args:
        inputs: Dictionary containing:
            - action (str): Operation to perform
            - file (str): Path to markdown file
            - id (int, optional): Item ID for single-item operations
            - description (str, optional): Item description

    Returns:
        Dictionary containing result, item, and/or items
    """
    action = inputs['action']
    file_path = os.path.expanduser(inputs.get('file', '/tmp/orac_todo.md'))
    item_id = inputs.get('id')
    description = inputs.get('description')

    actions = {
        'create': lambda: _create(file_path, description, immutable=False),
        'create_immutable': lambda: _create(file_path, description, immutable=True),
        'read': lambda: _read(file_path, item_id),
        'update': lambda: _update(file_path, item_id, description),
        'delete': lambda: _delete(file_path, item_id),
        'mark_complete': lambda: _mark_complete(file_path, item_id),
        'get_next': lambda: _get_next(file_path),
        'list_remaining': lambda: _list_remaining(file_path),
        'list_all': lambda: _list_all(file_path),
    }

    if action not in actions:
        raise ValueError(f"Unknown action: {action}. Valid: {list(actions.keys())}")

    return actions[action]()


def _load_todos(file_path: str) -> List[TodoItem]:
    """Load todos from markdown file."""
    if not os.path.exists(file_path):
        return []

    todos = []
    pattern = re.compile(
        r'^- \[([ x])\] #(\d+) (.+?)(\s+\[immutable\])?$'
    )

    with open(file_path, 'r') as f:
        for line in f:
            match = pattern.match(line.strip())
            if match:
                completed = match.group(1) == 'x'
                item_id = int(match.group(2))
                description = match.group(3).strip()
                immutable = match.group(4) is not None
                todos.append(TodoItem(
                    id=item_id,
                    description=description,
                    completed=completed,
                    immutable=immutable
                ))

    return todos


def _save_todos(file_path: str, todos: List[TodoItem]) -> None:
    """Save todos to markdown file."""
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)

    lines = ["# Todo List\n", "\n"]

    for item in sorted(todos, key=lambda x: x.id):
        checkbox = 'x' if item.completed else ' '
        immutable_tag = ' [immutable]' if item.immutable else ''
        lines.append(f"- [{checkbox}] #{item.id} {item.description}{immutable_tag}\n")

    with open(file_path, 'w') as f:
        f.writelines(lines)


def _get_next_id(todos: List[TodoItem]) -> int:
    """Get the next available ID."""
    if not todos:
        return 1
    return max(item.id for item in todos) + 1


def _create(file_path: str, description: str, immutable: bool) -> Dict[str, Any]:
    """Create a new todo item."""
    if not description:
        raise ValueError("Description is required for create")

    todos = _load_todos(file_path)
    new_id = _get_next_id(todos)

    item = TodoItem(
        id=new_id,
        description=description,
        completed=False,
        immutable=immutable
    )
    todos.append(item)
    _save_todos(file_path, todos)

    item_type = "immutable todo" if immutable else "todo"
    return {
        'result': f"Created {item_type} #{new_id}: {description}",
        'item': asdict(item),
        'items': None
    }


def _read(file_path: str, item_id: int) -> Dict[str, Any]:
    """Read a specific todo item."""
    if item_id is None:
        raise ValueError("ID is required for read")

    todos = _load_todos(file_path)
    for item in todos:
        if item.id == item_id:
            return {
                'result': f"#{item.id}: {item.description}",
                'item': asdict(item),
                'items': None
            }

    raise ValueError(f"Todo #{item_id} not found")


def _update(file_path: str, item_id: int, description: str) -> Dict[str, Any]:
    """Update a todo item's description."""
    if item_id is None:
        raise ValueError("ID is required for update")
    if not description:
        raise ValueError("Description is required for update")

    todos = _load_todos(file_path)
    for item in todos:
        if item.id == item_id:
            if item.immutable:
                raise ValueError(f"Cannot update immutable todo #{item_id}")
            item.description = description
            _save_todos(file_path, todos)
            return {
                'result': f"Updated #{item_id}: {description}",
                'item': asdict(item),
                'items': None
            }

    raise ValueError(f"Todo #{item_id} not found")


def _delete(file_path: str, item_id: int) -> Dict[str, Any]:
    """Delete a todo item."""
    if item_id is None:
        raise ValueError("ID is required for delete")

    todos = _load_todos(file_path)
    for i, item in enumerate(todos):
        if item.id == item_id:
            if item.immutable:
                raise ValueError(f"Cannot delete immutable todo #{item_id}")
            deleted = todos.pop(i)
            _save_todos(file_path, todos)
            return {
                'result': f"Deleted #{item_id}: {deleted.description}",
                'item': asdict(deleted),
                'items': None
            }

    raise ValueError(f"Todo #{item_id} not found")


def _mark_complete(file_path: str, item_id: int) -> Dict[str, Any]:
    """Mark a todo item as complete."""
    if item_id is None:
        raise ValueError("ID is required for mark_complete")

    todos = _load_todos(file_path)
    for item in todos:
        if item.id == item_id:
            if item.completed:
                return {
                    'result': f"#{item_id} already completed",
                    'item': asdict(item),
                    'items': None
                }
            item.completed = True
            _save_todos(file_path, todos)
            return {
                'result': f"Completed #{item_id}: {item.description}",
                'item': asdict(item),
                'items': None
            }

    raise ValueError(f"Todo #{item_id} not found")


def _get_next(file_path: str) -> Dict[str, Any]:
    """Get the next pending todo item."""
    todos = _load_todos(file_path)
    pending = [item for item in todos if not item.completed]

    if not pending:
        return {
            'result': "No pending todos",
            'item': None,
            'items': None
        }

    # Return the first pending item (lowest ID)
    next_item = min(pending, key=lambda x: x.id)
    return {
        'result': f"Next: #{next_item.id}: {next_item.description}",
        'item': asdict(next_item),
        'items': None
    }


def _list_remaining(file_path: str) -> Dict[str, Any]:
    """List all remaining (pending) todo items."""
    todos = _load_todos(file_path)
    pending = [item for item in todos if not item.completed]

    if not pending:
        return {
            'result': "No pending todos",
            'item': None,
            'items': []
        }

    lines = [f"#{item.id}: {item.description}" for item in sorted(pending, key=lambda x: x.id)]
    return {
        'result': f"{len(pending)} pending:\n" + "\n".join(lines),
        'item': None,
        'items': [asdict(item) for item in pending]
    }


def _list_all(file_path: str) -> Dict[str, Any]:
    """List all todo items."""
    todos = _load_todos(file_path)

    if not todos:
        return {
            'result': "No todos",
            'item': None,
            'items': []
        }

    lines = []
    for item in sorted(todos, key=lambda x: x.id):
        status = "✓" if item.completed else "○"
        lines.append(f"{status} #{item.id}: {item.description}")

    return {
        'result': f"{len(todos)} todos:\n" + "\n".join(lines),
        'item': None,
        'items': [asdict(item) for item in todos]
    }
