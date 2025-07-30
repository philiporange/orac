"""
Shared pytest fixtures and configuration for Orac tests.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch
import sys

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_llm_response():
    """Mock LLM API responses."""
    def _mock_response(response_text="Test response"):
        mock = Mock()
        mock.return_value = response_text
        return mock
    return _mock_response


@pytest.fixture
def test_prompts_dir(temp_dir):
    """Create test prompts directory with sample prompts."""
    prompts_dir = temp_dir / "prompts"
    prompts_dir.mkdir()

    # Create test prompts
    (prompts_dir / "test_prompt.yaml").write_text("""
prompt: "Test prompt: ${param}"
parameters:
  - name: param
    type: string
    default: "default_value"
""")

    (prompts_dir / "capital.yaml").write_text("""
prompt: "What is the capital of ${country}?"
parameters:
  - name: country
    type: string
    description: "Country name"
    default: "France"
""")

    (prompts_dir / "recipe.yaml").write_text("""
prompt: "Give me a recipe for ${dish}"
parameters:
  - name: dish
    type: string
    description: "Dish to make a recipe for"
    default: "pancakes"
response_mime_type: "application/json"
""")

    return prompts_dir


@pytest.fixture
def test_skills_dir(temp_dir):
    """Create test skills directory with sample skills."""
    skills_dir = temp_dir / "skills"
    skills_dir.mkdir()

    # Create test calculator skill YAML
    (skills_dir / "calculator.yaml").write_text("""
name: calculator
description: "Simple calculator skill"
version: "1.0.0"
inputs:
  - name: expression
    type: string
    description: "Mathematical expression to evaluate"
    required: true
outputs:
  - name: result
    type: string
    description: "Calculation result"
metadata:
  author: "Test"
security:
  timeout: 10
""")

    # Create test calculator skill Python script
    (skills_dir / "calculator.py").write_text("""
def execute(inputs):
    \"\"\"Execute calculator skill.\"\"\"
    expression = inputs.get('expression', '')
    try:
        # Simple evaluation for test purposes
        result = str(eval(expression))
        return {"result": result}
    except Exception as e:
        return {"result": f"Error: {str(e)}"}
""")

    return skills_dir




@pytest.fixture(autouse=True)
def setup_test_env(monkeypatch):
    """Set up test environment variables."""
    monkeypatch.setenv("ORAC_LLM_PROVIDER", "google")
    monkeypatch.setenv("ORAC_DISABLE_DOTENV", "1")
    monkeypatch.setenv("GOOGLE_API_KEY", "test_api_key")


@pytest.fixture
def mock_api_response():
    """Mock API response for testing."""
    def _create_mock(content="Test response", json_content=None):
        with patch('orac.client.call_api') as mock_call:
            if json_content:
                mock_call.return_value = json_content
            else:
                mock_call.return_value = content
            yield mock_call
    return _create_mock


@pytest.fixture
def sample_test_files(temp_dir):
    """Create sample test files for file upload tests."""
    files_dir = temp_dir / "files"
    files_dir.mkdir()
    
    # Create a text file
    (files_dir / "test.txt").write_text("This is a test file.")
    
    # Create a JSON file
    (files_dir / "test.json").write_text('{"key": "value"}')
    
    return files_dir