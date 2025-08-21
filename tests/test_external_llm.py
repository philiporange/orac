"""
External LLM integration tests that make real API calls.

These tests require actual API keys and make real calls to external services.
They are marked as 'external' and can be run separately with:
    pytest -m external

Set GOOGLE_API_KEY or other provider keys to run these tests.
"""

import pytest
import json
import os
import orac
from orac.prompt import Prompt
from orac.config import Provider


@pytest.fixture(scope="module")
def external_client():
    """Initialize orac with Google provider for external tests."""
    # Initialize orac with Google provider using environment API key
    orac.init(
        default_provider=Provider.GOOGLE,
        providers={
            Provider.GOOGLE: {"api_key_env": "GOOGLE_API_KEY"}
        },
        interactive=False
    )
    yield
    # Clean up
    orac.reset()


@pytest.mark.external
@pytest.mark.skipif(
    not os.environ.get("GOOGLE_API_KEY"), 
    reason="GOOGLE_API_KEY not set - external LLM test requires API key"
)
def test_recipe_prompt_external(external_client):
    """Test recipe prompt with external Google API call."""
    # Create prompt instance - provider already set by external_client
    recipe = Prompt("recipe")
    
    # Make real API call
    result = recipe.completion(dish="chocolate chip cookies")
    
    # Verify response structure and content
    assert result is not None
    assert len(result.strip()) > 0
    
    # Since recipe prompt returns JSON, parse and verify structure
    try:
        recipe_data = json.loads(result)
        assert isinstance(recipe_data, dict)
        assert "title" in recipe_data
        assert "ingredients" in recipe_data
        assert "steps" in recipe_data
        assert isinstance(recipe_data["ingredients"], list)
        assert isinstance(recipe_data["steps"], list)
        assert len(recipe_data["ingredients"]) > 0
        assert len(recipe_data["steps"]) > 0
        
        # Verify content mentions cookies
        title_lower = recipe_data["title"].lower()
        assert "cookie" in title_lower or "chocolate" in title_lower
        
    except json.JSONDecodeError:
        pytest.fail(f"Recipe prompt should return valid JSON, got: {result}")


@pytest.mark.external
@pytest.mark.skipif(
    not os.environ.get("GOOGLE_API_KEY"), 
    reason="GOOGLE_API_KEY not set - external LLM test requires API key"
)
def test_recipe_prompt_callable_interface(external_client):
    """Test recipe prompt using callable interface with external API."""
    recipe = Prompt("recipe")
    
    # Use callable interface
    result = recipe(dish="banana bread")
    
    # Should auto-detect JSON and return dict
    assert isinstance(result, dict)
    assert "title" in result
    assert "ingredients" in result
    assert "steps" in result
    
    # Check content is relevant
    title_lower = result["title"].lower()
    assert "banana" in title_lower or "bread" in title_lower