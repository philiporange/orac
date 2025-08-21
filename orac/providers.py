"""Provider registry for multi-provider LLM support.

This module manages multiple LLM provider configurations and provides
a unified interface for client creation with explicit consent management.
"""

from __future__ import annotations

from typing import Dict, Optional, Any
from dataclasses import dataclass
from openai import OpenAI

from .config import Config, Provider
from .auth import AuthManager


@dataclass
class ClientConfig:
    """Configuration for an OpenAI-compatible client."""
    provider: Provider
    api_key: str
    base_url: str
    model_name: Optional[str] = None
    client: Optional[OpenAI] = None


class ProviderRegistry:
    """Registry for managing multiple LLM providers."""
    
    def __init__(self, auth_manager: Optional[AuthManager] = None):
        """Initialize ProviderRegistry.
        
        Args:
            auth_manager: AuthManager instance. Creates new one if None.
        """
        self._auth_manager = auth_manager or AuthManager()
        self._active_providers: Dict[Provider, ClientConfig] = {}
        self._default_provider: Optional[Provider] = None
    
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
        """Add a provider with explicit key source.
        
        Args:
            provider: The provider to add
            api_key: Direct API key (no consent needed)
            api_key_env: Environment variable name for API key
            allow_env: Allow reading from default environment variable
            from_config: Allow reading from stored config
            base_url: Custom base URL (optional)
            model_name: Custom model name for this provider
            interactive: Allow interactive consent prompting
            
        Raises:
            ValueError: If no valid API key source
            PermissionError: If consent required but not granted
        """
        # Request consent if needed for environment access
        if (allow_env or from_config) and interactive:
            if not self._auth_manager.request_consent(provider, interactive=True):
                raise PermissionError(f"Consent denied for {provider.value}")
        
        # Get API key using AuthManager
        try:
            resolved_api_key = self._auth_manager.get_api_key(
                provider,
                api_key=api_key,
                api_key_env=api_key_env,
                allow_env=allow_env,
                from_config=from_config
            )
        except (ValueError, PermissionError) as e:
            raise e
        
        # Get base URL
        if base_url is None:
            resolved_base_url = self._auth_manager.get_base_url(provider)
        else:
            resolved_base_url = base_url
        
        # Get model name
        resolved_model_name = model_name or Config.get_default_model_name()
        
        # Create client config
        config = ClientConfig(
            provider=provider,
            api_key=resolved_api_key,
            base_url=resolved_base_url,
            model_name=resolved_model_name
        )
        
        self._active_providers[provider] = config
        
        # Set as default if this is the first provider
        if self._default_provider is None:
            self._default_provider = provider
    
    def remove_provider(self, provider: Provider) -> bool:
        """Remove a provider from the registry.
        
        Args:
            provider: The provider to remove
            
        Returns:
            True if provider was removed, False if it wasn't registered
        """
        if provider not in self._active_providers:
            return False
        
        # Close client if it exists
        config = self._active_providers[provider]
        if config.client:
            # OpenAI client doesn't need explicit closing
            pass
        
        del self._active_providers[provider]
        
        # Update default provider if necessary
        if self._default_provider == provider:
            self._default_provider = next(iter(self._active_providers), None)
        
        return True
    
    def set_default_provider(self, provider: Provider) -> None:
        """Set default provider.
        
        Args:
            provider: The provider to set as default
            
        Raises:
            ValueError: If provider is not registered
        """
        if provider not in self._active_providers:
            raise ValueError(f"Provider {provider.value} is not registered")
        
        self._default_provider = provider
    
    def get_default_provider(self) -> Optional[Provider]:
        """Get the default provider.
        
        Returns:
            Default provider or None if no providers registered
        """
        return self._default_provider
    
    def get_client(self, provider: Optional[Provider] = None) -> OpenAI:
        """Get OpenAI client for provider.
        
        Args:
            provider: Provider to get client for. Uses default if None.
            
        Returns:
            OpenAI client instance
            
        Raises:
            ValueError: If no providers registered or provider not found
            RuntimeError: If no default provider set
        """
        # Determine which provider to use
        target_provider = provider or self._default_provider
        
        if target_provider is None:
            raise RuntimeError("No default provider set. Call set_default_provider() or specify provider.")
        
        if target_provider not in self._active_providers:
            raise ValueError(f"Provider {target_provider.value} is not registered")
        
        config = self._active_providers[target_provider]
        
        # Create client if not cached
        if config.client is None:
            config.client = OpenAI(
                api_key=config.api_key,
                base_url=config.base_url
            )
        
        return config.client
    
    def get_model_name(self, provider: Optional[Provider] = None) -> str:
        """Get model name for provider.
        
        Args:
            provider: Provider to get model for. Uses default if None.
            
        Returns:
            Model name string
            
        Raises:
            ValueError: If provider not registered
            RuntimeError: If no default provider set
        """
        target_provider = provider or self._default_provider
        
        if target_provider is None:
            raise RuntimeError("No default provider set")
        
        if target_provider not in self._active_providers:
            raise ValueError(f"Provider {target_provider.value} is not registered")
        
        return self._active_providers[target_provider].model_name
    
    def get_registered_providers(self) -> list[Provider]:
        """Get list of registered providers.
        
        Returns:
            List of registered Provider enums
        """
        return list(self._active_providers.keys())
    
    def is_provider_registered(self, provider: Provider) -> bool:
        """Check if a provider is registered.
        
        Args:
            provider: The provider to check
            
        Returns:
            True if registered, False otherwise
        """
        return provider in self._active_providers
    
    def get_provider_info(self, provider: Provider) -> Optional[Dict[str, Any]]:
        """Get information about a registered provider.
        
        Args:
            provider: The provider to get info for
            
        Returns:
            Dictionary with provider info or None if not registered
        """
        if provider not in self._active_providers:
            return None
        
        config = self._active_providers[provider]
        return {
            "provider": provider.value,
            "base_url": config.base_url,
            "model_name": config.model_name,
            "has_client": config.client is not None,
            "is_default": provider == self._default_provider
        }
    
    def get_registry_status(self) -> Dict[str, Any]:
        """Get complete registry status.
        
        Returns:
            Dictionary with full registry information
        """
        return {
            "default_provider": self._default_provider.value if self._default_provider else None,
            "registered_providers": len(self._active_providers),
            "providers": {
                provider.value: self.get_provider_info(provider)
                for provider in self._active_providers
            }
        }