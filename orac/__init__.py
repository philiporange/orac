"""Orac: A lightweight, YAML-driven framework for LLM interactions.

This module provides the main package-level API with explicit initialization
and consent management following PyPI best practices.
"""

from __future__ import annotations

from typing import Optional, Dict, Any
from .config import Provider
from .client import Client
from .auth import AuthManager
from .prompt import Prompt
from .flow import Flow
from .agent import Agent
from .skill import Skill


# Global client instance for convenience
_global_client: Optional[Client] = None


def init(
    *,
    interactive: bool = True,
    default_provider: Provider = Provider.OPENROUTER,
    providers: Optional[Dict[Provider, Dict[str, Any]]] = None
) -> Client:
    """Initialize Orac with explicit consent.
    
    Args:
        interactive: Allow interactive consent prompting
        default_provider: Default provider to use (recommended: OpenRouter)
        providers: Dictionary mapping providers to their configuration
        
    Returns:
        Initialized Client instance
        
    Example:
        >>> import orac
        >>> client = orac.init(interactive=True)
        >>> # or with specific providers
        >>> client = orac.init(providers={
        ...     orac.Provider.OPENROUTER: {"allow_env": True},
        ...     orac.Provider.OPENAI: {"api_key_env": "OPENAI_API_KEY"}
        ... })
    """
    global _global_client
    
    client = Client()
    
    if providers:
        for provider, config in providers.items():
            client.add_provider(provider, interactive=interactive, **config)
    else:
        # Default: try recommended provider with consent
        client.add_provider(default_provider, allow_env=True, interactive=interactive)
    
    client.set_default_provider(default_provider)
    _global_client = client
    return client


def quick_init(provider: Provider, *, api_key: str) -> Client:
    """Quick init with direct API key (no consent needed).
    
    Args:
        provider: The provider to initialize
        api_key: Direct API key
        
    Returns:
        Initialized Client instance
        
    Example:
        >>> import orac
        >>> client = orac.quick_init(orac.Provider.OPENAI, api_key="sk-...")
    """
    global _global_client
    
    client = Client()
    client.add_provider(provider, api_key=api_key)
    client.set_default_provider(provider)
    _global_client = client
    return client


def get_client() -> Client:
    """Get global client (must call init() first).
    
    Returns:
        Global Client instance
        
    Raises:
        RuntimeError: If no global client has been initialized
    """
    if _global_client is None:
        raise RuntimeError(
            "Must call orac.init() or orac.quick_init() before using global client"
        )
    return _global_client


def is_initialized() -> bool:
    """Check if global client is initialized.
    
    Returns:
        True if global client exists, False otherwise
    """
    return _global_client is not None


def reset() -> None:
    """Reset global client state.
    
    This clears the global client, requiring re-initialization.
    Useful for testing or changing authentication configuration.
    """
    global _global_client
    _global_client = None


# Export main classes and types
__all__ = [
    # Main classes
    "Prompt", 
    "Flow", 
    "Agent", 
    "Skill", 
    "Client",
    "AuthManager",
    "Provider",
    
    # Package-level functions
    "init",
    "quick_init", 
    "get_client",
    "is_initialized",
    "reset",
]