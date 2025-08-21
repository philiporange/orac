"""
Tests for main Orac functionality with new authentication system.

This module tests:
- Prompt class with new client-based authentication
- Flow execution with new auth system
- Package-level API (orac.init, orac.quick_init, etc.)
- Integration between components
- Error handling and validation
"""

import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import orac
from orac import Prompt, Flow, Client, AuthManager, Provider
from orac.config import Config


class TestPackageLevelAPI:
    """Test the package-level authentication API."""
    
    def test_orac_init_not_called_initially(self):
        """Test that orac is not initialized by default."""
        # Reset global state
        orac.reset()
        assert not orac.is_initialized()
        
        with pytest.raises(RuntimeError, match="Must call.*init"):
            orac.get_client()
    
    def test_orac_quick_init(self):
        """Test orac.quick_init with direct API key."""
        orac.reset()
        
        client = orac.quick_init(Provider.GOOGLE, api_key="test-key")
        
        assert orac.is_initialized()
        assert client is orac.get_client()
        assert client.is_initialized()
        assert Provider.GOOGLE in client.get_registered_providers()
        
        # Clean up
        orac.reset()
    
    def test_orac_init_with_consent(self):
        """Test orac.init with consent flow."""
        orac.reset()
        
        # Test that with consent and environment variable, init works
        import tempfile
        from pathlib import Path
        
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict('os.environ', {'GOOGLE_API_KEY': 'test_env_key'}):
                consent_file = Path(tmpdir) / "consent.json"
                auth_manager = orac.AuthManager(consent_file)
                auth_manager.grant_consent(Provider.GOOGLE)
                
                # Create client manually (simulating what orac.init would do)
                client = orac.Client(auth_manager)
                client.add_provider(Provider.GOOGLE, allow_env=True, interactive=False)
                
                # Set global client
                orac._global_client = client
                
                assert orac.is_initialized()
                assert client.is_initialized()
                assert Provider.GOOGLE in client.get_registered_providers()
        
        # Clean up
        orac.reset()
    
    def test_orac_reset(self):
        """Test orac.reset() clears global state."""
        # Initialize first
        orac.quick_init(Provider.GOOGLE, api_key="test")
        assert orac.is_initialized()
        
        # Reset
        orac.reset()
        assert not orac.is_initialized()
        
        with pytest.raises(RuntimeError):
            orac.get_client()


class TestPromptWithNewAuth:
    """Test Prompt class with new authentication system."""
    
    @pytest.fixture(autouse=True)
    def setup(self, temp_dir, test_client):
        """Set up test environment."""
        self.temp_dir = temp_dir
        self.client = test_client
        
        # Create test prompts directory
        self.prompts_dir = temp_dir / "prompts"
        self.prompts_dir.mkdir()
        
        # Create test prompt files
        (self.prompts_dir / "capital.yaml").write_text("""
prompt: "What is the capital of ${country}?"
parameters:
  - name: country
    type: string
    description: "Country name"
    default: "France"
""")
        
        (self.prompts_dir / "recipe.yaml").write_text("""
prompt: "Give me a recipe for ${dish}"
parameters:
  - name: dish
    type: string
    default: "pancakes"
response_mime_type: "application/json"
""")
    
    def test_prompt_requires_client(self):
        """Test that Prompt requires client or global client."""
        orac.reset()
        
        # Should fail without client or global client
        with pytest.raises(ValueError, match="No client provided"):
            Prompt("capital", prompts_dir=str(self.prompts_dir))
    
    def test_prompt_with_explicit_client(self):
        """Test Prompt with explicit client."""
        prompt = Prompt(
            "capital", 
            client=self.client, 
            prompts_dir=str(self.prompts_dir)
        )
        
        assert prompt.client is self.client
        assert prompt.prompt_name == "capital"
    
    def test_prompt_with_global_client(self, mock_global_client):
        """Test Prompt with global client."""
        prompt = Prompt("capital", prompts_dir=str(self.prompts_dir))
        
        assert prompt.client is mock_global_client
        assert prompt.prompt_name == "capital"
    
    @patch('orac.client.Client.chat')
    def test_prompt_completion(self, mock_chat):
        """Test prompt completion with new auth system."""
        mock_chat.return_value = "Paris"
        
        prompt = Prompt(
            "capital", 
            client=self.client, 
            prompts_dir=str(self.prompts_dir)
        )
        result = prompt.completion(country="France")
        
        assert result == "Paris"
        mock_chat.assert_called_once()
        
        # Verify the call arguments
        call_args = mock_chat.call_args
        assert len(call_args[1]['message_history']) == 1
        assert "France" in call_args[1]['message_history'][0]['text']
    
    @patch('orac.client.Client.chat')
    def test_prompt_with_provider_override(self, mock_chat):
        """Test prompt with provider override."""
        mock_chat.return_value = "Tokyo"
        
        # Add another provider to client
        self.client.add_provider(Provider.OPENAI, api_key="test_openai_key")
        
        prompt = Prompt(
            "capital", 
            client=self.client, 
            prompts_dir=str(self.prompts_dir)
        )
        result = prompt.completion(country="Japan", provider=Provider.OPENAI)
        
        assert result == "Tokyo"
        
        # Verify provider was passed
        call_args = mock_chat.call_args
        assert call_args[1]['provider'] == Provider.OPENAI
    
    @patch('orac.client.Client.chat')
    def test_prompt_json_response(self, mock_chat):
        """Test prompt with JSON response."""
        mock_response = '{"recipe": "Mix ingredients", "time": "30 mins"}'
        mock_chat.return_value = mock_response
        
        prompt = Prompt(
            "recipe", 
            client=self.client, 
            prompts_dir=str(self.prompts_dir)
        )
        result = prompt.completion(dish="cookies")
        
        # Should return the JSON string
        assert result == mock_response
    
    def test_prompt_parameter_validation(self):
        """Test prompt parameter validation."""
        prompt = Prompt(
            "capital", 
            client=self.client, 
            prompts_dir=str(self.prompts_dir)
        )
        
        # Test parameter resolution
        params = prompt._resolve_parameters(country="Spain")
        assert params["country"] == "Spain"
        
        # Test default parameter
        params_default = prompt._resolve_parameters()
        assert params_default["country"] == "France"  # default from YAML


class TestClientIntegration:
    """Test Client class functionality."""
    
    @pytest.fixture(autouse=True)
    def setup(self, temp_dir):
        """Set up test environment."""
        self.temp_dir = temp_dir
        self.auth_manager = AuthManager(temp_dir / "consent.json")
        self.client = Client(self.auth_manager)
    
    def test_client_initialization(self):
        """Test client initialization states."""
        # Initially not initialized
        assert not self.client.is_initialized()
        
        # Add provider
        self.client.add_provider(Provider.GOOGLE, api_key="test_key")
        assert self.client.is_initialized()
        assert len(self.client.get_registered_providers()) == 1
    
    def test_client_multi_provider(self):
        """Test multi-provider functionality."""
        # Add multiple providers
        self.client.add_provider(Provider.GOOGLE, api_key="google_key")
        self.client.add_provider(Provider.OPENAI, api_key="openai_key")
        
        providers = self.client.get_registered_providers()
        assert len(providers) == 2
        assert Provider.GOOGLE in providers
        assert Provider.OPENAI in providers
        
        # Test default provider
        assert self.client.get_default_provider() == Provider.GOOGLE  # first added
        
        # Change default
        self.client.set_default_provider(Provider.OPENAI)
        assert self.client.get_default_provider() == Provider.OPENAI
    
    def test_client_remove_provider(self):
        """Test removing providers."""
        self.client.add_provider(Provider.GOOGLE, api_key="google_key")
        self.client.add_provider(Provider.OPENAI, api_key="openai_key")
        
        assert len(self.client.get_registered_providers()) == 2
        
        # Remove one provider
        result = self.client.remove_provider(Provider.OPENAI)
        assert result is True
        assert len(self.client.get_registered_providers()) == 1
        assert Provider.OPENAI not in self.client.get_registered_providers()
        
        # Try to remove non-existent provider
        result = self.client.remove_provider(Provider.ANTHROPIC)
        assert result is False
    
    @patch('orac.client.call_api')
    def test_client_completion(self, mock_call_api):
        """Test client completion method."""
        mock_call_api.return_value = "Test response"
        
        self.client.add_provider(Provider.GOOGLE, api_key="test_key")
        
        # Make sure the mock is being called
        result = self.client.completion("Test prompt")
        assert result == "Test response"
        
        # Verify call_api was called correctly
        assert mock_call_api.called, "Mock was not called - real API call made instead"
        mock_call_api.assert_called_once()
        call_args = mock_call_api.call_args
        assert call_args[0][0] is self.client.get_provider_registry()  # provider_registry
    
    @patch('orac.client.call_api')
    def test_client_chat(self, mock_call_api):
        """Test client chat method."""
        mock_call_api.return_value = "Chat response"
        
        self.client.add_provider(Provider.GOOGLE, api_key="test_key")
        
        message_history = [{"role": "user", "text": "Hello"}]
        result = self.client.chat(message_history)
        
        assert result == "Chat response"
        assert mock_call_api.called, "Mock was not called - real API call made instead"
        mock_call_api.assert_called_once()
    
    def test_client_without_providers_fails(self):
        """Test that client fails without providers."""
        with pytest.raises(RuntimeError, match="must have at least one provider"):
            self.client.completion("Test prompt")


class TestAuthManagerIntegration:
    """Test AuthManager integration."""
    
    @pytest.fixture(autouse=True)
    def setup(self, temp_dir):
        """Set up test environment."""
        self.temp_dir = temp_dir
        self.consent_file = temp_dir / "consent.json"
        self.auth_manager = AuthManager(self.consent_file)
    
    def test_consent_persistence(self):
        """Test that consent is persisted across AuthManager instances."""
        # Grant consent
        self.auth_manager.grant_consent(Provider.GOOGLE)
        assert self.auth_manager.has_consent(Provider.GOOGLE)
        
        # Create new AuthManager with same file
        new_auth_manager = AuthManager(self.consent_file)
        assert new_auth_manager.has_consent(Provider.GOOGLE)
    
    def test_consent_workflow(self):
        """Test complete consent workflow."""
        # Initially no consent
        assert not self.auth_manager.has_consent(Provider.OPENAI)
        assert len(self.auth_manager.get_consented_providers()) == 0
        
        # Grant consent
        self.auth_manager.grant_consent(Provider.OPENAI)
        assert self.auth_manager.has_consent(Provider.OPENAI)
        assert Provider.OPENAI in self.auth_manager.get_consented_providers()
        
        # Check status
        status = self.auth_manager.show_consent_status()
        assert status["providers"]["openai"]["consent_granted"]
        assert status["providers"]["openai"]["consent_timestamp"] is not None
        
        # Revoke consent
        result = self.auth_manager.revoke_consent(Provider.OPENAI)
        assert result is True
        assert not self.auth_manager.has_consent(Provider.OPENAI)
    
    def test_api_key_sources(self, monkeypatch):
        """Test different API key sources."""
        # Direct API key (no consent needed)
        key = self.auth_manager.get_api_key(Provider.GOOGLE, api_key="direct_key")
        assert key == "direct_key"
        
        # Environment variable (with consent)
        monkeypatch.setenv("TEST_KEY", "env_key")
        self.auth_manager.grant_consent(Provider.GOOGLE)
        
        key = self.auth_manager.get_api_key(Provider.GOOGLE, api_key_env="TEST_KEY")
        assert key == "env_key"
        
        # Default environment access (requires consent)
        monkeypatch.setenv("GOOGLE_API_KEY", "default_env_key")
        key = self.auth_manager.get_api_key(Provider.GOOGLE, allow_env=True)
        assert key == "default_env_key"
        
        # Without consent should fail
        self.auth_manager.revoke_consent(Provider.GOOGLE)
        with pytest.raises(PermissionError, match="[Cc]onsent"):
            self.auth_manager.get_api_key(Provider.GOOGLE, allow_env=True)


class TestErrorHandling:
    """Test error handling in new auth system."""
    
    def test_invalid_provider(self):
        """Test handling of invalid providers."""
        with pytest.raises(ValueError):
            Provider("invalid_provider")
    
    def test_client_status_reporting(self, test_client):
        """Test client status reporting."""
        status = test_client.get_client_status()
        
        assert "initialized" in status
        assert "registry_status" in status
        assert "consent_status" in status
        
        assert status["initialized"] is True
        assert status["registry_status"]["registered_providers"] == 1
    
    def test_prompt_with_missing_file(self, test_client, temp_dir):
        """Test prompt with missing YAML file."""
        with pytest.raises(FileNotFoundError):
            Prompt("nonexistent", client=test_client, prompts_dir=str(temp_dir))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])