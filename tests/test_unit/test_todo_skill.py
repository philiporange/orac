"""
Unit tests for the todo skill.
"""

import pytest
import tempfile
import os
from pathlib import Path

from orac.skills.todo import execute, _load_todos, _save_todos, TodoItem


class TestTodoSkill:
    """Unit tests for the todo skill."""

    @pytest.fixture
    def todo_file(self):
        """Create a temporary todo file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            yield f.name
        if os.path.exists(f.name):
            os.unlink(f.name)

    @pytest.mark.unit
    def test_create_todo(self, todo_file):
        """Test creating a new todo item."""
        result = execute({
            'action': 'create',
            'file': todo_file,
            'description': 'Test task'
        })

        assert result['item']['id'] == 1
        assert result['item']['description'] == 'Test task'
        assert result['item']['completed'] is False
        assert result['item']['immutable'] is False

    @pytest.mark.unit
    def test_create_immutable_todo(self, todo_file):
        """Test creating an immutable todo item."""
        result = execute({
            'action': 'create_immutable',
            'file': todo_file,
            'description': 'Immutable task'
        })

        assert result['item']['id'] == 1
        assert result['item']['immutable'] is True

    @pytest.mark.unit
    def test_create_increments_id(self, todo_file):
        """Test that IDs increment correctly."""
        execute({'action': 'create', 'file': todo_file, 'description': 'First'})
        execute({'action': 'create', 'file': todo_file, 'description': 'Second'})
        result = execute({'action': 'create', 'file': todo_file, 'description': 'Third'})

        assert result['item']['id'] == 3

    @pytest.mark.unit
    def test_read_todo(self, todo_file):
        """Test reading a specific todo item."""
        execute({'action': 'create', 'file': todo_file, 'description': 'Read me'})

        result = execute({
            'action': 'read',
            'file': todo_file,
            'id': 1
        })

        assert result['item']['description'] == 'Read me'

    @pytest.mark.unit
    def test_read_nonexistent_raises_error(self, todo_file):
        """Test that reading a nonexistent item raises an error."""
        with pytest.raises(ValueError, match="not found"):
            execute({'action': 'read', 'file': todo_file, 'id': 999})

    @pytest.mark.unit
    def test_update_todo(self, todo_file):
        """Test updating a todo item."""
        execute({'action': 'create', 'file': todo_file, 'description': 'Original'})

        result = execute({
            'action': 'update',
            'file': todo_file,
            'id': 1,
            'description': 'Updated'
        })

        assert result['item']['description'] == 'Updated'

    @pytest.mark.unit
    def test_update_immutable_raises_error(self, todo_file):
        """Test that updating an immutable item raises an error."""
        execute({'action': 'create_immutable', 'file': todo_file, 'description': 'Locked'})

        with pytest.raises(ValueError, match="Cannot update immutable"):
            execute({
                'action': 'update',
                'file': todo_file,
                'id': 1,
                'description': 'Try to change'
            })

    @pytest.mark.unit
    def test_delete_todo(self, todo_file):
        """Test deleting a todo item."""
        execute({'action': 'create', 'file': todo_file, 'description': 'Delete me'})

        result = execute({
            'action': 'delete',
            'file': todo_file,
            'id': 1
        })

        assert 'Deleted' in result['result']

        # Verify it's gone
        with pytest.raises(ValueError, match="not found"):
            execute({'action': 'read', 'file': todo_file, 'id': 1})

    @pytest.mark.unit
    def test_delete_immutable_raises_error(self, todo_file):
        """Test that deleting an immutable item raises an error."""
        execute({'action': 'create_immutable', 'file': todo_file, 'description': 'Locked'})

        with pytest.raises(ValueError, match="Cannot delete immutable"):
            execute({'action': 'delete', 'file': todo_file, 'id': 1})

    @pytest.mark.unit
    def test_mark_complete(self, todo_file):
        """Test marking a todo as complete."""
        execute({'action': 'create', 'file': todo_file, 'description': 'Complete me'})

        result = execute({
            'action': 'mark_complete',
            'file': todo_file,
            'id': 1
        })

        assert result['item']['completed'] is True

    @pytest.mark.unit
    def test_mark_complete_immutable(self, todo_file):
        """Test that immutable items can be marked complete."""
        execute({'action': 'create_immutable', 'file': todo_file, 'description': 'Immutable'})

        result = execute({
            'action': 'mark_complete',
            'file': todo_file,
            'id': 1
        })

        assert result['item']['completed'] is True

    @pytest.mark.unit
    def test_get_next_returns_first_pending(self, todo_file):
        """Test that get_next returns the first pending item."""
        execute({'action': 'create', 'file': todo_file, 'description': 'First'})
        execute({'action': 'create', 'file': todo_file, 'description': 'Second'})
        execute({'action': 'mark_complete', 'file': todo_file, 'id': 1})

        result = execute({'action': 'get_next', 'file': todo_file})

        assert result['item']['id'] == 2
        assert result['item']['description'] == 'Second'

    @pytest.mark.unit
    def test_get_next_empty_list(self, todo_file):
        """Test get_next with no pending items."""
        result = execute({'action': 'get_next', 'file': todo_file})

        assert result['item'] is None
        assert 'No pending' in result['result']

    @pytest.mark.unit
    def test_list_remaining(self, todo_file):
        """Test listing remaining (pending) items."""
        execute({'action': 'create', 'file': todo_file, 'description': 'First'})
        execute({'action': 'create', 'file': todo_file, 'description': 'Second'})
        execute({'action': 'create', 'file': todo_file, 'description': 'Third'})
        execute({'action': 'mark_complete', 'file': todo_file, 'id': 2})

        result = execute({'action': 'list_remaining', 'file': todo_file})

        assert len(result['items']) == 2
        ids = [item['id'] for item in result['items']]
        assert 1 in ids
        assert 3 in ids
        assert 2 not in ids

    @pytest.mark.unit
    def test_list_all(self, todo_file):
        """Test listing all items."""
        execute({'action': 'create', 'file': todo_file, 'description': 'First'})
        execute({'action': 'create', 'file': todo_file, 'description': 'Second'})
        execute({'action': 'mark_complete', 'file': todo_file, 'id': 1})

        result = execute({'action': 'list_all', 'file': todo_file})

        assert len(result['items']) == 2

    @pytest.mark.unit
    def test_markdown_format(self, todo_file):
        """Test that the markdown file is correctly formatted."""
        execute({'action': 'create', 'file': todo_file, 'description': 'Normal task'})
        execute({'action': 'create_immutable', 'file': todo_file, 'description': 'Locked task'})
        execute({'action': 'mark_complete', 'file': todo_file, 'id': 1})

        with open(todo_file, 'r') as f:
            content = f.read()

        assert '# Todo List' in content
        assert '- [x] #1 Normal task' in content
        assert '- [ ] #2 Locked task [immutable]' in content

    @pytest.mark.unit
    def test_unknown_action_raises_error(self, todo_file):
        """Test that unknown action raises an error."""
        with pytest.raises(ValueError, match="Unknown action"):
            execute({'action': 'invalid', 'file': todo_file})

    @pytest.mark.unit
    def test_create_without_description_raises_error(self, todo_file):
        """Test that create without description raises an error."""
        with pytest.raises(ValueError, match="Description is required"):
            execute({'action': 'create', 'file': todo_file})
