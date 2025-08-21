"""Test consent flow and authentication management."""

import tempfile
import os
from pathlib import Path
import pytest

from orac.auth import AuthManager
from orac.config import Provider
from orac.client import Client


class TestConsentFlow:
    """Test consent management functionality."""
    
    def test_consent_required_for_env_access(self):
        """Test that environment access requires consent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            consent_file = Path(tmpdir) / "consent.json"
            auth_manager = AuthManager(consent_file)
            
            # Should not have consent initially
            assert not auth_manager.has_consent(Provider.OPENAI)
            assert len(auth_manager.get_consented_providers()) == 0
            
            # Should fail to get API key without consent
            with pytest.raises(PermissionError, match="[Cc]onsent"):
                auth_manager.get_api_key(Provider.OPENAI, allow_env=True)
    
    def test_consent_persistence(self):
        """Test that consent is properly saved and loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            consent_file = Path(tmpdir) / "consent.json"
            
            # Create first auth manager and grant consent
            auth_manager1 = AuthManager(consent_file)
            auth_manager1.grant_consent(Provider.OPENAI)
            
            assert auth_manager1.has_consent(Provider.OPENAI)
            assert Provider.OPENAI in auth_manager1.get_consented_providers()
            
            # Create second auth manager - should load persisted consent
            auth_manager2 = AuthManager(consent_file)
            assert auth_manager2.has_consent(Provider.OPENAI)
            assert Provider.OPENAI in auth_manager2.get_consented_providers()
    
    def test_consent_revocation(self):
        """Test that consent can be revoked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            consent_file = Path(tmpdir) / "consent.json"
            auth_manager = AuthManager(consent_file)
            
            # Grant consent
            auth_manager.grant_consent(Provider.OPENAI)
            assert auth_manager.has_consent(Provider.OPENAI)
            
            # Revoke consent
            result = auth_manager.revoke_consent(Provider.OPENAI)
            assert result is True
            assert not auth_manager.has_consent(Provider.OPENAI)
            
            # Revoking non-existent consent should return False
            result = auth_manager.revoke_consent(Provider.GOOGLE)
            assert result is False
    
    def test_api_key_sources(self):
        """Test different API key sources."""
        # Save original environment state
        original_openai_key = os.environ.get("OPENAI_API_KEY")
        try:
            # Clean up any existing OPENAI_API_KEY for this test
            if "OPENAI_API_KEY" in os.environ:
                del os.environ["OPENAI_API_KEY"]
            
                with tempfile.TemporaryDirectory() as tmpdir:
                    consent_file = Path(tmpdir) / "consent.json"
                    auth_manager = AuthManager(consent_file)
                    
                    # Direct API key should work without consent
                    key = auth_manager.get_api_key(Provider.OPENAI, api_key="direct-key")
                    assert key == "direct-key"
                    
                    # Environment variable should work
                    os.environ["TEST_KEY"] = "env-key"
                    key = auth_manager.get_api_key(Provider.OPENAI, api_key_env="TEST_KEY")
                    assert key == "env-key"
                    del os.environ["TEST_KEY"]
                    
                    # Default environment should require consent
                    auth_manager.grant_consent(Provider.OPENAI)
                    
                    # Test with missing environment variable
                    with pytest.raises(ValueError, match="not found"):
                        auth_manager.get_api_key(Provider.OPENAI, allow_env=True)
        finally:
            # Restore original environment state
            if original_openai_key is not None:
                os.environ["OPENAI_API_KEY"] = original_openai_key
    
    def test_consent_status_reporting(self):
        """Test consent status reporting."""
        with tempfile.TemporaryDirectory() as tmpdir:
            consent_file = Path(tmpdir) / "consent.json"
            auth_manager = AuthManager(consent_file)
            
            # Initial status
            status = auth_manager.show_consent_status()
            assert status["consent_file"] == str(consent_file)
            assert not status["providers"]["openai"]["consent_granted"]
            
            # After granting consent
            auth_manager.grant_consent(Provider.OPENAI)
            status = auth_manager.show_consent_status()
            assert status["providers"]["openai"]["consent_granted"]
            assert status["providers"]["openai"]["consent_timestamp"] is not None


class TestClientIntegration:
    """Test Client integration with consent system."""
    
    def test_client_with_direct_api_key(self):
        """Test client with direct API key (no consent needed)."""
        client = Client()
        
        # Should work without consent for direct API key
        client.add_provider(Provider.OPENAI, api_key="test-key")
        
        assert client.is_initialized()
        assert Provider.OPENAI in client.get_registered_providers()
    
    def test_client_with_consent_required(self):
        """Test client requiring consent."""
        # Save original environment state
        original_openai_key = os.environ.get("OPENAI_API_KEY")
        try:
            # Clean up any existing OPENAI_API_KEY for this test
            if "OPENAI_API_KEY" in os.environ:
                del os.environ["OPENAI_API_KEY"]
            
                with tempfile.TemporaryDirectory() as tmpdir:
                    consent_file = Path(tmpdir) / "consent.json"
                    auth_manager = AuthManager(consent_file)
                    client = Client(auth_manager)
                    
                    # Should fail without consent
                    with pytest.raises(PermissionError, match="[Cc]onsent"):
                        client.add_provider(Provider.OPENAI, allow_env=True, interactive=False)
                    
                    # Grant consent and try again
                    auth_manager.grant_consent(Provider.OPENAI)
                    
                    # Should still fail due to missing environment variable
                    with pytest.raises(ValueError, match="not found"):
                        client.add_provider(Provider.OPENAI, allow_env=True, interactive=False)
        finally:
            # Restore original environment state
            if original_openai_key is not None:
                os.environ["OPENAI_API_KEY"] = original_openai_key
    
    def test_client_multi_provider(self):
        """Test client with multiple providers."""
        client = Client()
        
        # Add multiple providers
        client.add_provider(Provider.OPENAI, api_key="openai-key")
        client.add_provider(Provider.GOOGLE, api_key="google-key")
        
        assert len(client.get_registered_providers()) == 2
        assert Provider.OPENAI in client.get_registered_providers()
        assert Provider.GOOGLE in client.get_registered_providers()
        
        # Test default provider
        assert client.get_default_provider() == Provider.OPENAI  # First added becomes default
        
        client.set_default_provider(Provider.GOOGLE)
        assert client.get_default_provider() == Provider.GOOGLE
    
    def test_client_status_reporting(self):
        """Test client status reporting."""
        with tempfile.TemporaryDirectory() as tmpdir:
            consent_file = Path(tmpdir) / "consent.json"
            auth_manager = AuthManager(consent_file)
            client = Client(auth_manager)
            
            # Initial status
            status = client.get_client_status()
            assert not status["initialized"]
            assert status["registry_status"]["registered_providers"] == 0
            
            # After adding provider
            client.add_provider(Provider.OPENAI, api_key="test-key")
            status = client.get_client_status()
            assert status["initialized"]
            assert status["registry_status"]["registered_providers"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])