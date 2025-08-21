"""Main Client class for Orac with explicit initialization.

This module provides the primary Client interface that requires explicit 
initialization and consent management, following PyPI best practices.
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any
from pathlib import Path

from .config import Config, Provider
from .auth import AuthManager
from .providers import ProviderRegistry
from .openai_client import call_api
from .logger import logger


class Client:
    """Main Orac client with explicit initialization and multi-provider support."""
    
    def __init__(self, auth_manager: Optional[AuthManager] = None):
        """Initialize Client with optional AuthManager.
        
        Args:
            auth_manager: AuthManager instance. Creates new one if None.
        """
        self._auth_manager = auth_manager or AuthManager()
        self._provider_registry = ProviderRegistry(self._auth_manager)
        self._initialized = False
    
    def add_provider(
        self, 
        provider: Provider, 
        *,
        api_key: Optional[str] = None,
        api_key_env: Optional[str] = None,
        allow_env: bool = False, 
        from_config: bool = False,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        interactive: bool = False
    ) -> None:
        """Add provider with explicit consent.
        
        Args:
            provider: The provider to add
            api_key: Direct API key (no consent needed)
            api_key_env: Environment variable name for API key
            allow_env: Allow reading from default environment variable (requires consent)
            from_config: Allow reading from stored config (requires consent)
            base_url: Custom base URL (optional)
            model_name: Custom model name for this provider
            interactive: Allow interactive consent prompting
            
        Raises:
            PermissionError: If consent is required but denied
            ValueError: If no valid API key source provided
        """
        self._provider_registry.add_provider(
            provider,
            api_key=api_key,
            api_key_env=api_key_env,
            allow_env=allow_env,
            from_config=from_config,
            base_url=base_url,
            model_name=model_name,
            interactive=interactive
        )
        self._initialized = True
        
        logger.info(f"Added provider {provider.value} to client")
    
    def remove_provider(self, provider: Provider) -> bool:
        """Remove provider from client.
        
        Args:
            provider: The provider to remove
            
        Returns:
            True if provider was removed, False if not registered
        """
        result = self._provider_registry.remove_provider(provider)
        
        # Check if we still have providers
        if not self._provider_registry.get_registered_providers():
            self._initialized = False
        
        if result:
            logger.info(f"Removed provider {provider.value} from client")
        
        return result
    
    def set_default_provider(self, provider: Provider) -> None:
        """Set default provider.
        
        Args:
            provider: The provider to set as default
            
        Raises:
            ValueError: If provider is not registered
        """
        self._provider_registry.set_default_provider(provider)
        logger.info(f"Set default provider to {provider.value}")
    
    def get_default_provider(self) -> Optional[Provider]:
        """Get the default provider.
        
        Returns:
            Default provider or None if no providers registered
        """
        return self._provider_registry.get_default_provider()
    
    def get_registered_providers(self) -> List[Provider]:
        """Get list of registered providers.
        
        Returns:
            List of registered Provider enums
        """
        return self._provider_registry.get_registered_providers()
    
    def is_initialized(self) -> bool:
        """Check if client is initialized (has at least one provider).
        
        Returns:
            True if initialized, False otherwise
        """
        return self._initialized
    
    def completion(
        self,
        prompt: str,
        provider: Optional[Provider] = None,
        *,
        system_prompt: Optional[str] = None,
        model_name: Optional[str] = None,
        generation_config: Optional[Dict[str, Any]] = None,
        file_paths: Optional[List[str]] = None
    ) -> str:
        """Make completion request.
        
        Args:
            prompt: The prompt text
            provider: Provider to use (uses default if None)
            system_prompt: Optional system prompt
            model_name: Optional model override
            generation_config: Optional generation parameters
            file_paths: Optional list of file paths to attach
            
        Returns:
            LLM response text
            
        Raises:
            RuntimeError: If client is not initialized
        """
        if not self._initialized:
            raise RuntimeError("Client must have at least one provider. Call add_provider() first.")
        
        # Convert to message history format expected by call_api
        message_history = [{"role": "user", "text": prompt}]
        
        return call_api(
            self._provider_registry,
            provider=provider,
            message_history=message_history,
            system_prompt=system_prompt,
            model_name=model_name,
            generation_config=generation_config,
            file_paths=file_paths
        )
    
    def chat(
        self,
        message_history: List[Dict[str, Any]],
        provider: Optional[Provider] = None,
        *,
        system_prompt: Optional[str] = None,
        model_name: Optional[str] = None,
        generation_config: Optional[Dict[str, Any]] = None,
        file_paths: Optional[List[str]] = None
    ) -> str:
        """Make chat request with message history.
        
        Args:
            message_history: List of message dictionaries with 'role' and 'text' keys
            provider: Provider to use (uses default if None)
            system_prompt: Optional system prompt
            model_name: Optional model override
            generation_config: Optional generation parameters
            file_paths: Optional list of file paths to attach
            
        Returns:
            LLM response text
            
        Raises:
            RuntimeError: If client is not initialized
        """
        if not self._initialized:
            raise RuntimeError("Client must have at least one provider. Call add_provider() first.")
        
        return call_api(
            self._provider_registry,
            provider=provider,
            message_history=message_history,
            system_prompt=system_prompt,
            model_name=model_name,
            generation_config=generation_config,
            file_paths=file_paths
        )
    
    def get_client_status(self) -> Dict[str, Any]:
        """Get comprehensive client status.
        
        Returns:
            Dictionary with client status information
        """
        return {
            "initialized": self._initialized,
            "registry_status": self._provider_registry.get_registry_status(),
            "consent_status": self._auth_manager.show_consent_status()
        }
    
    def get_auth_manager(self) -> AuthManager:
        """Get the underlying AuthManager.
        
        Returns:
            AuthManager instance
        """
        return self._auth_manager
    
    def get_provider_registry(self) -> ProviderRegistry:
        """Get the underlying ProviderRegistry.
        
        Returns:
            ProviderRegistry instance
        """
        return self._provider_registry