"""
Unit tests for the config module.
"""

import pytest
import os
from pathlib import Path

from orac.config import Config, Provider


class TestConfig:
    """Unit tests for configuration management."""

    @pytest.mark.unit
    def test_config_is_not_instantiable(self):
        """Test that Config class cannot be instantiated."""
        with pytest.raises(TypeError, match="cannot be instantiated"):
            Config()

    @pytest.mark.unit
    def test_config_is_not_mutable(self):
        """Test that Config attributes cannot be changed."""
        # The Config class uses Final annotations to prevent mutation at type level
        # We can't directly test runtime mutation prevention on class attributes
        # since Python doesn't enforce Final at runtime, so we test the __setattr__ method
        config_instance = object.__new__(Config)
        with pytest.raises(AttributeError, match="read-only"):
            config_instance.__setattr__("test", "value")

    @pytest.mark.unit
    def test_default_model_name(self):
        """Test default model name configuration."""
        assert isinstance(Config.DEFAULT_MODEL_NAME, str)
        assert len(Config.DEFAULT_MODEL_NAME) > 0

    @pytest.mark.unit
    def test_paths_are_path_objects(self):
        """Test that path configurations are Path objects."""
        assert isinstance(Config.PACKAGE_DIR, Path)
        assert isinstance(Config.PROJECT_ROOT, Path)
        assert isinstance(Config.DEFAULT_PROMPTS_DIR, Path)
        assert isinstance(Config.DEFAULT_FLOWS_DIR, Path)
        assert isinstance(Config.LOG_FILE, Path)

    @pytest.mark.unit
    def test_reserved_client_kwargs(self):
        """Test reserved client kwargs configuration."""
        assert isinstance(Config.RESERVED_CLIENT_KWARGS, set)
        assert "model_name" in Config.RESERVED_CLIENT_KWARGS
        assert "api_key" in Config.RESERVED_CLIENT_KWARGS

    @pytest.mark.unit
    def test_supported_types(self):
        """Test supported parameter types configuration."""
        assert isinstance(Config.SUPPORTED_TYPES, dict)
        assert Config.SUPPORTED_TYPES["string"] == str
        assert Config.SUPPORTED_TYPES["int"] == int
        assert Config.SUPPORTED_TYPES["bool"] == bool

    @pytest.mark.unit
    def test_conversation_settings(self):
        """Test conversation-related configuration."""
        assert isinstance(Config.CONVERSATION_DB, Path)
        assert isinstance(Config.DEFAULT_CONVERSATION_MODE, bool)
        assert isinstance(Config.MAX_CONVERSATION_HISTORY, int)
        assert Config.MAX_CONVERSATION_HISTORY > 0

    @pytest.mark.unit
    def test_provider_enum(self):
        """Test Provider enum values."""
        assert Provider.GOOGLE == "google"
        assert Provider.OPENAI == "openai"
        assert Provider.ANTHROPIC == "anthropic"
        assert Provider.AZURE == "azure"
        assert Provider.OPENROUTER == "openrouter"
        assert Provider.CUSTOM == "custom"

    @pytest.mark.unit
    def test_config_with_env_override(self, monkeypatch):
        """Test that environment variables override defaults."""
        # Test model name override
        monkeypatch.setenv("ORAC_DEFAULT_MODEL_NAME", "test-model")
        # Import config again to pick up env var
        import importlib
        from orac import config
        importlib.reload(config)
        
        assert config.Config.DEFAULT_MODEL_NAME == "test-model"

    @pytest.mark.unit 
    def test_download_dir_creation(self):
        """Test that download directory is configured."""
        assert isinstance(Config.DOWNLOAD_DIR, Path)
        # Should be a valid path (may not exist yet)
        assert len(str(Config.DOWNLOAD_DIR)) > 0