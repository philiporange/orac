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
        "base_url": os.getenv("AZURE_OPENAI_BASE", ""),
        "key_env": "AZURE_OPENAI_KEY",
    },
    Provider.OPENROUTER: {
        "base_url": "https://openrouter.ai/api/v1/",
        "key_env": "OPENROUTER_API_KEY",
    },
}

# Optional but **explicit** provider selection via env var
LLM_PROVIDER: Provider | None = (
    Provider(os.getenv("ORAC_LLM_PROVIDER")) if os.getenv("ORAC_LLM_PROVIDER") else None
)


class Config:
    """Namespace that exposes project-wide constants as *class attributes*."""

    # ------------------------------------------------------------------ #
    # Paths                                                              #
    # ------------------------------------------------------------------ #
    PACKAGE_DIR: Final[Path] = Path(__file__).resolve().parent
    PROJECT_ROOT: Final[Path] = PACKAGE_DIR.parent
    DEFAULT_PROMPTS_DIR: Final[Path] = Path(
        os.getenv("ORAC_DEFAULT_PROMPTS_DIR", PACKAGE_DIR / "prompts")
    )
    DEFAULT_CONFIG_FILE: Final[Path] = Path(
        os.getenv("ORAC_DEFAULT_CONFIG_FILE", PACKAGE_DIR / "config.yaml")
    )

    # ------------------------------------------------------------------ #
    # LLM-client defaults                                                #
    # ------------------------------------------------------------------ #
    DEFAULT_MODEL_NAME: Final[str] = os.getenv(
        "ORAC_DEFAULT_MODEL_NAME", "gemini-2.0-flash"
    )

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
    DOWNLOAD_DIR: Final[Path] = Path(
        os.getenv("ORAC_DOWNLOAD_DIR", tempfile.mkdtemp(prefix="orac_dl_"))
    )

    # ------------------------------------------------------------------ #
    # Logging                                                            #
    # ------------------------------------------------------------------ #
    LOG_FILE: Final[Path] = Path(os.getenv("ORAC_LOG_FILE", PROJECT_ROOT / "llm.log"))

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
