"""Centralised, *read-only* constants for the **Orac** project.

Usage
-----
>>> from orac.config import Config
>>> Config.DEFAULT_PROMPTS_DIR
PosixPath('.../prompts')
>>> Config.DEFAULT_MODEL_NAME
'gemini-2.0-flash'

The class is intentionally *not* instantiable and blocks mutation to guarantee
that settings remain immutable throughout the program’s lifetime.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Final
from enum import Enum

__all__: Final[list[str]] = ["Config", "Provider"]


class Provider(str, Enum):
    OPENAI = "openai"
    GOOGLE = "google"
    ANTHROPIC = "anthropic"
    AZURE = "azure"
    OPENROUTER = "openrouter"
    ZAI = "z.ai"
    CLI = "cli"
    CUSTOM = "custom"


# Hard-coded defaults for known providers
_PROVIDER_DEFAULTS: dict[Provider, dict[str, str]] = {
    Provider.OPENAI: {
        "base_url": "https://api.openai.com/v1/",
        "key_env": "OPENAI_API_KEY",
    },
    Provider.GOOGLE: {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_env": "GOOGLE_API_KEY",
    },
    Provider.ANTHROPIC: {
        "base_url": "https://api.anthropic.com/v1/",
        "key_env": "ANTHROPIC_API_KEY",
    },
    Provider.AZURE: {
        "base_url": "",  # Will be read from AZURE_OPENAI_BASE when needed
        "key_env": "AZURE_OPENAI_KEY",
    },
    Provider.OPENROUTER: {
        "base_url": "https://openrouter.ai/api/v1/",
        "key_env": "OPENROUTER_API_KEY",
    },
    Provider.ZAI: {
        "base_url": "https://api.z.ai/api/coding/paas/v4",
        "key_env": "ZAI_API_KEY",
    },
    Provider.CLI: {
        "base_url": "http://10.0.0.10:8317/v1/chat/completions",
        "key_env": "CLI_API_KEY",
    }
}

# Provider selection moved to methods to avoid import-time env access


class Config:
    """Namespace that exposes project-wide constants as *class attributes*."""

    # ------------------------------------------------------------------ #
    # Paths                                                              #
    # ------------------------------------------------------------------ #
    PACKAGE_DIR: Final[Path] = Path(__file__).resolve().parent
    PROJECT_ROOT: Final[Path] = PACKAGE_DIR.parent

    # ------------------------------------------------------------------ #
    # LLM-client defaults                                                #
    # ------------------------------------------------------------------ #
    _DEFAULT_MODEL_NAME: Final[str] = "gemini-2.5-flash-lite"

    # ------------------------------------------------------------------ #
    # LLM-wrapper helpers                                                #
    # ------------------------------------------------------------------ #
    RESERVED_CLIENT_KWARGS: Final[set[str]] = {
        "model_name",
        "api_key",
        "generation_config",
        "system_prompt",
        "response_mime_type",
        "response_schema",
    }

    SUPPORTED_TYPES: Final[dict[str, type]] = {
        "str": str,
        "string": str,
        "int": int,
        "integer": int,
        "float": float,
        "number": float,
        "bool": bool,
        "boolean": bool,
        "list": list,
        "array": list,
    }

    # Global temp dir used by LLM wrappers for remote downloads
    _DOWNLOAD_DIR_PREFIX: Final[str] = "orac_dl_"

    # ------------------------------------------------------------------ #
    # Logging                                                            #
    # ------------------------------------------------------------------ #
    _DEFAULT_LOG_FILE: Final[str] = "llm.log"

    # ------------------------------------------------------------------ #
    # Conversation settings                                              #
    # ------------------------------------------------------------------ #
    _DEFAULT_CONVERSATION_DB_NAME: Final[str] = "conversations.db"
    _DEFAULT_CONVERSATION_MODE: Final[bool] = False
    _DEFAULT_MAX_CONVERSATION_HISTORY: Final[int] = 20

    # ------------------------------------------------------------------ #
    # Methods that read environment - only when explicitly called       #
    # ------------------------------------------------------------------ #
    @classmethod
    def get_provider_from_env(cls) -> Provider | None:
        """Get provider from environment."""
        return None
    
    @classmethod
    def get_default_model_name(cls) -> str:
        """Get default model name from environment or use default."""
        return os.getenv("ORAC_DEFAULT_MODEL_NAME", cls._DEFAULT_MODEL_NAME)
    
    @classmethod
    def get_log_file_path(cls) -> Path:
        """Get log file path from environment or use default."""
        return Path(os.getenv("ORAC_LOG_FILE", cls.PROJECT_ROOT / cls._DEFAULT_LOG_FILE))
    
    @classmethod
    def get_download_dir(cls) -> Path:
        """Get download directory from environment or create temp dir."""
        return Path(os.getenv("ORAC_DOWNLOAD_DIR", tempfile.mkdtemp(prefix=cls._DOWNLOAD_DIR_PREFIX)))
    
    @classmethod
    def get_prompts_dir(cls) -> Path:
        """Get prompts directory from environment or use default."""
        return Path(os.getenv("ORAC_DEFAULT_PROMPTS_DIR", cls.PACKAGE_DIR / "prompts"))
    
    @classmethod
    def get_flows_dir(cls) -> Path:
        """Get flows directory from environment or use default."""
        return Path(os.getenv("ORAC_DEFAULT_FLOWS_DIR", cls.PACKAGE_DIR / "flows"))
    
    @classmethod
    def get_skills_dir(cls) -> Path:
        """Get skills directory from environment or use default."""
        return Path(os.getenv("ORAC_DEFAULT_SKILLS_DIR", cls.PACKAGE_DIR / "skills"))
    
    @classmethod
    def get_agents_dir(cls) -> Path:
        """Get agents directory from environment or use default."""
        return Path(os.getenv("ORAC_DEFAULT_AGENTS_DIR", cls.PACKAGE_DIR / "agents"))
    
    @classmethod
    def get_config_file(cls) -> Path:
        """Get config file from environment or use default."""
        return Path(os.getenv("ORAC_DEFAULT_CONFIG_FILE", cls.PACKAGE_DIR / "config.yaml"))
    
    @classmethod
    def get_conversation_db_path(cls) -> Path:
        """Get conversation database path from environment or use default."""
        return Path(os.getenv("ORAC_CONVERSATION_DB", Path.home() / ".orac" / cls._DEFAULT_CONVERSATION_DB_NAME))
    
    @classmethod
    def get_default_conversation_mode(cls) -> bool:
        """Get default conversation mode from environment or use default."""
        return os.getenv("ORAC_DEFAULT_CONVERSATION_MODE", "false").lower() in ("true", "1", "yes")
    
    @classmethod
    def get_max_conversation_history(cls) -> int:
        """Get max conversation history from environment or use default."""
        try:
            return int(os.getenv("ORAC_MAX_CONVERSATION_HISTORY", str(cls._DEFAULT_MAX_CONVERSATION_HISTORY)))
        except ValueError:
            return cls._DEFAULT_MAX_CONVERSATION_HISTORY
    
    @classmethod
    def get_azure_base_url(cls) -> str:
        """Get Azure OpenAI base URL from environment."""
        return os.getenv("AZURE_OPENAI_BASE", "")

    # ------------------------------------------------------------------ #
    # Dunder methods                                                     #
    # ------------------------------------------------------------------ #
    __slots__ = ()

    def __new__(cls, *_, **__) -> "Config":
        """Prevent instantiation – use as a static namespace instead."""
        raise TypeError(
            "`Config` cannot be instantiated; use class attributes directly."
        )

    def __setattr__(self, *_: object) -> None:  # noqa: D401
        """Disallow runtime mutation of configuration values."""
        raise AttributeError("Config is read-only – do not mutate class attributes.")
