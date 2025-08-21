"""Test import safety - ensure no side effects at import time."""

import subprocess
import sys
import tempfile
import os
from pathlib import Path
import pytest


def test_no_import_side_effects():
    """Ensure importing orac has no side effects (no environment access)."""
    # Test that importing doesn't read environment variables
    script = """
import orac
print("Import successful - no side effects")
"""
    
    # Run in completely clean environment
    result = subprocess.run([
        sys.executable, "-c", script
    ], env={"PATH": os.environ.get("PATH", "")}, capture_output=True, text=True)
    
    assert result.returncode == 0
    assert "Import successful" in result.stdout
    assert result.stderr == ""


def test_config_methods_dont_break_without_env():
    """Test that Config methods work even without environment variables."""
    script = """
from orac.config import Config

# Test that all methods return reasonable defaults
print("prompts_dir:", Config.get_prompts_dir())
print("model_name:", Config.get_default_model_name())
print("provider_from_env:", Config.get_provider_from_env())
print("log_file:", Config.get_log_file_path())
print("conversation_mode:", Config.get_default_conversation_mode())
print("max_history:", Config.get_max_conversation_history())
print("All config methods work without environment")
"""
    
    result = subprocess.run([
        sys.executable, "-c", script
    ], env={"PATH": os.environ.get("PATH", "")}, capture_output=True, text=True)
    
    assert result.returncode == 0
    assert "All config methods work" in result.stdout


def test_requires_explicit_init():
    """Test that API calls require explicit initialization."""
    script = """
try:
    import orac
    # This should fail - no global client initialized
    client = orac.get_client()
    print("ERROR: Should have failed!")
except RuntimeError as e:
    if "Must call" in str(e) and "init" in str(e):
        print("PASS: Correctly requires initialization")
    else:
        print(f"ERROR: Wrong error message: {e}")
except Exception as e:
    print(f"ERROR: Unexpected exception: {e}")
"""
    
    result = subprocess.run([
        sys.executable, "-c", script
    ], env={}, capture_output=True, text=True)
    
    assert result.returncode == 0
    assert "PASS: Correctly requires initialization" in result.stdout


def test_prompt_requires_client():
    """Test that Prompt class requires client."""
    script = """
try:
    from orac import Prompt
    # This should fail - no client provided and no global client
    prompt = Prompt("test")
    print("ERROR: Should have failed!")
except ValueError as e:
    if "No client provided" in str(e) and "no global client" in str(e):
        print("PASS: Prompt correctly requires client")
    else:
        print(f"ERROR: Wrong error message: {e}")
except Exception as e:
    print(f"ERROR: Unexpected exception: {e}")
"""
    
    result = subprocess.run([
        sys.executable, "-c", script
    ], env={}, capture_output=True, text=True)
    
    assert result.returncode == 0
    assert "PASS: Prompt correctly requires client" in result.stdout


def test_auth_manager_no_auto_env_access():
    """Test that AuthManager doesn't automatically access environment."""
    with tempfile.TemporaryDirectory() as tmpdir:
        consent_file = Path(tmpdir) / "consent.json"
        
        script = f"""
from orac.auth import AuthManager
from orac.config import Provider

# Create AuthManager with custom consent file
auth_manager = AuthManager(consent_file="{consent_file}")

# Should not have any consent by default (no auto environment reading)
providers = auth_manager.get_consented_providers()
if len(providers) == 0:
    print("PASS: No automatic consent granted")
else:
    print(f"ERROR: Unexpected consent: {{providers}}")

# Should require explicit consent for environment access
try:
    auth_manager.get_api_key(Provider.OPENAI, allow_env=True)
    print("ERROR: Should have required consent")
except Exception as e:
    if "consent" in str(e).lower():
        print("PASS: Environment access requires consent")
    else:
        print(f"ERROR: Wrong error: {{e}}")
"""
        
        result = subprocess.run([
            sys.executable, "-c", script
        ], env={}, capture_output=True, text=True)
        
        assert result.returncode == 0
        assert "PASS: No automatic consent granted" in result.stdout
        assert "PASS: Environment access requires consent" in result.stdout


def test_client_requires_explicit_provider():
    """Test that Client requires explicit provider setup."""
    script = """
from orac.client import Client

client = Client()

# Should not be initialized without providers
if not client.is_initialized():
    print("PASS: Client not initialized without providers")
else:
    print("ERROR: Client should not be initialized")

# Should fail completion without providers
try:
    client.completion("test prompt")
    print("ERROR: Should have failed without providers")
except RuntimeError as e:
    if "must have at least one provider" in str(e).lower():
        print("PASS: Correctly requires provider setup")
    else:
        print(f"ERROR: Wrong error: {e}")
"""
    
    result = subprocess.run([
        sys.executable, "-c", script
    ], env={}, capture_output=True, text=True)
    
    assert result.returncode == 0
    assert "PASS: Client not initialized without providers" in result.stdout
    assert "PASS: Correctly requires provider setup" in result.stdout


if __name__ == "__main__":
    # Run tests directly
    test_no_import_side_effects()
    test_config_methods_dont_break_without_env()
    test_requires_explicit_init()
    test_prompt_requires_client()
    test_auth_manager_no_auto_env_access()
    test_client_requires_explicit_provider()
    print("All import safety tests passed!")