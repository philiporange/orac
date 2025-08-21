"""Authentication and consent management for Orac.

This module provides secure API key management with explicit user consent,
following PyPI best practices by avoiding automatic environment access.
"""

from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

from .config import Config, Provider, _PROVIDER_DEFAULTS


@dataclass
class ProviderAuth:
    """Authentication configuration for a provider."""
    provider: Provider
    api_key: Optional[str] = None
    api_key_env: Optional[str] = None
    base_url: Optional[str] = None
    consent_granted: bool = False
    consent_timestamp: Optional[datetime] = None


class AuthManager:
    """Manages authentication and consent for LLM providers."""
    
    def __init__(self, consent_file: Optional[Path] = None):
        """Initialize AuthManager with consent file location.
        
        Args:
            consent_file: Path to consent file. Defaults to ~/.config/orac/consent.json
        """
        if consent_file is None:
            consent_file = Path.home() / ".config" / "orac" / "consent.json"
        
        self._consent_file = Path(consent_file)
        self._providers: Dict[Provider, ProviderAuth] = {}
        self._ensure_consent_dir()
        self._load_consent()
    
    def _ensure_consent_dir(self) -> None:
        """Ensure consent file directory exists."""
        self._consent_file.parent.mkdir(parents=True, exist_ok=True)
    
    def _load_consent(self) -> None:
        """Load consent data from file."""
        if not self._consent_file.exists():
            return
        
        try:
            with open(self._consent_file, 'r') as f:
                data = json.load(f)
            
            for provider_name, config in data.get("providers", {}).items():
                try:
                    provider = Provider(provider_name)
                    consent_ts = None
                    if config.get("consent_timestamp"):
                        consent_ts = datetime.fromisoformat(config["consent_timestamp"])
                    
                    self._providers[provider] = ProviderAuth(
                        provider=provider,
                        api_key_env=config.get("api_key_env"),
                        base_url=config.get("base_url"),
                        consent_granted=config.get("consent_granted", False),
                        consent_timestamp=consent_ts
                    )
                except ValueError:
                    # Skip invalid provider names
                    continue
        except Exception:
            # If consent file is corrupted, start fresh
            pass
    
    def _save_consent(self) -> None:
        """Save consent data to file."""
        data = {"providers": {}}
        
        for provider, auth in self._providers.items():
            data["providers"][provider.value] = {
                "api_key_env": auth.api_key_env,
                "base_url": auth.base_url,
                "consent_granted": auth.consent_granted,
                "consent_timestamp": auth.consent_timestamp.isoformat() if auth.consent_timestamp else None,
            }
        
        try:
            with open(self._consent_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            # Fail silently if we can't save consent
            pass
    
    def request_consent(self, provider: Provider, interactive: bool = False) -> bool:
        """Request consent to use API key for provider.
        
        Args:
            provider: The LLM provider to request consent for
            interactive: If True, prompt user for consent
            
        Returns:
            True if consent was granted, False otherwise
        """
        # Check if we already have consent
        if self.has_consent(provider):
            return True
        
        if not interactive:
            return False
        
        # Interactive consent request
        provider_name = provider.value.title()
        print(f"\nOrac needs access to {provider_name} API to function.")
        print(f"This will read your {_PROVIDER_DEFAULTS[provider]['key_env']} environment variable.")
        print("Your API key will never be stored permanently.")
        print("You can revoke this consent anytime with 'orac auth consent revoke'.")
        
        response = input(f"Grant consent to use {provider_name} API? [y/N]: ")
        
        if response.lower() in ("y", "yes"):
            self._grant_consent(provider)
            return True
        
        return False
    
    def _grant_consent(self, provider: Provider) -> None:
        """Grant consent for a provider."""
        if provider not in self._providers:
            self._providers[provider] = ProviderAuth(provider=provider)
        
        self._providers[provider].consent_granted = True
        self._providers[provider].consent_timestamp = datetime.now()
        self._providers[provider].api_key_env = _PROVIDER_DEFAULTS[provider]["key_env"]
        
        # Set base URL from defaults or environment for Azure
        if provider == Provider.AZURE:
            self._providers[provider].base_url = Config.get_azure_base_url()
        else:
            self._providers[provider].base_url = _PROVIDER_DEFAULTS[provider]["base_url"]
        
        self._save_consent()
    
    def grant_consent(self, provider: Provider) -> None:
        """Programmatically grant consent for a provider."""
        self._grant_consent(provider)
    
    def revoke_consent(self, provider: Provider) -> bool:
        """Revoke consent for a provider.
        
        Args:
            provider: The provider to revoke consent for
            
        Returns:
            True if consent was revoked, False if no consent existed
        """
        if provider not in self._providers:
            return False
        
        self._providers[provider].consent_granted = False
        self._providers[provider].consent_timestamp = None
        self._save_consent()
        return True
    
    def has_consent(self, provider: Provider) -> bool:
        """Check if we have consent to use provider's API key.
        
        Args:
            provider: The provider to check consent for
            
        Returns:
            True if consent is granted, False otherwise
        """
        return (
            provider in self._providers 
            and self._providers[provider].consent_granted
        )
    
    def get_consented_providers(self) -> List[Provider]:
        """Get list of providers with active consent."""
        return [
            provider for provider, auth in self._providers.items()
            if auth.consent_granted
        ]
    
    def get_api_key(
        self,
        provider: Provider,
        *,
        api_key: Optional[str] = None,
        api_key_env: Optional[str] = None,
        allow_env: bool = False,
        from_config: bool = False
    ) -> str:
        """Get API key with explicit source specification.
        
        Args:
            provider: The provider to get API key for
            api_key: Direct API key (takes precedence)
            api_key_env: Environment variable name to read from
            allow_env: Allow reading from default environment variable
            from_config: Allow reading from stored config (requires consent)
            
        Returns:
            API key string
            
        Raises:
            ValueError: If no valid API key source is found
            PermissionError: If consent is required but not granted
        """
        # 1. Direct API key takes precedence
        if api_key:
            return api_key
        
        # 2. Explicit environment variable name
        if api_key_env:
            key = os.getenv(api_key_env)
            if key:
                return key
            raise ValueError(f"API key not found in environment variable: {api_key_env}")
        
        # 3. Read from config (requires consent)
        if from_config:
            if not self.has_consent(provider):
                raise PermissionError(f"Consent required to read {provider.value} API key from config")
            
            if provider in self._providers and self._providers[provider].api_key_env:
                key = os.getenv(self._providers[provider].api_key_env)
                if key:
                    return key
                raise ValueError(f"API key not found in environment variable: {self._providers[provider].api_key_env}")
        
        # 4. Allow default environment variable (requires consent for environment access)
        if allow_env:
            if not self.has_consent(provider):
                raise PermissionError(f"Consent required to read {provider.value} API key from environment")
            
            default_env = _PROVIDER_DEFAULTS[provider]["key_env"]
            key = os.getenv(default_env)
            if key:
                return key
            raise ValueError(f"API key not found in default environment variable: {default_env}")
        
        raise ValueError(
            f"No API key source specified for {provider.value}. "
            "Provide api_key, api_key_env, or set allow_env=True with consent."
        )
    
    def get_base_url(self, provider: Provider) -> str:
        """Get base URL for provider.
        
        Args:
            provider: The provider to get base URL for
            
        Returns:
            Base URL string
        """
        # Check if we have custom base URL in config
        if provider in self._providers and self._providers[provider].base_url:
            return self._providers[provider].base_url
        
        # Use default or get from environment for Azure
        if provider == Provider.AZURE:
            return Config.get_azure_base_url()
        
        return _PROVIDER_DEFAULTS[provider]["base_url"]
    
    def get_provider_auth(self, provider: Provider) -> Optional[ProviderAuth]:
        """Get authentication configuration for a provider.
        
        Args:
            provider: The provider to get config for
            
        Returns:
            ProviderAuth if exists, None otherwise
        """
        return self._providers.get(provider)
    
    def show_consent_status(self) -> Dict[str, Any]:
        """Get consent status for all providers.
        
        Returns:
            Dictionary with consent status information
        """
        status = {
            "consent_file": str(self._consent_file),
            "providers": {}
        }
        
        for provider in Provider:
            auth = self._providers.get(provider)
            if auth:
                status["providers"][provider.value] = {
                    "consent_granted": auth.consent_granted,
                    "consent_timestamp": auth.consent_timestamp.isoformat() if auth.consent_timestamp else None,
                    "api_key_env": auth.api_key_env,
                    "base_url": auth.base_url,
                }
            else:
                status["providers"][provider.value] = {
                    "consent_granted": False,
                    "consent_timestamp": None,
                    "api_key_env": None,
                    "base_url": None,
                }
        
        return status