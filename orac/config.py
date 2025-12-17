"""Centralised configuration for the **Orac** project.

Provides layered configuration with precedence (highest to lowest):
1. Runtime arguments (CLI flags, completion() args)
2. Resource YAML (prompt.yaml, agent.yaml, flow.yaml)
3. Project config (./.orac/config.yaml)
4. User config (~/.config/orac/config.yaml)
5. Provider defaults (hard-coded)

Resource directories are searched in order (highest priority first):
1. Project resources (./.orac/prompts/, ./.orac/flows/, etc.)
2. User resources (~/.config/orac/prompts/, ~/.config/orac/flows/, etc.)
3. Package resources (orac/prompts/, orac/flows/, etc.)

Directory structure:
    ~/.config/orac/
        config.yaml          # User-level defaults
        consent.json         # API consent records
        prompts/             # User's custom prompts
        flows/               # User's custom flows
        skills/              # User's custom skills
        agents/              # User's custom agents

    ./.orac/                 # Project-specific (in project root)
        config.yaml          # Project-level defaults
        prompts/             # Project prompts (override user/package)
        flows/               # Project flows
        skills/              # Project skills
        agents/              # Project agents

Usage
-----
>>> from orac.config import Config, ConfigLoader
>>> Config.get_prompts_dir()
PosixPath('.../prompts')
>>> loader = ConfigLoader()
>>> loader.get('provider')
'openrouter'
"""

from __future__ import annotations

import os
import tempfile
import yaml
from pathlib import Path
from copy import deepcopy
from typing import Final, Optional, Dict, Any
from enum import Enum

__all__: Final[list[str]] = ["Config", "Provider", "ConfigLoader"]


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
        "base_url": "http://10.0.0.10:8317/v1/",
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
    _DEFAULT_MODEL_NAME: Final[str] = "gemini-3-flash-preview"

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
    
    # User config directory
    _USER_CONFIG_DIR: Final[Path] = Path.home() / ".config" / "orac"

    @classmethod
    def get_prompts_dir(cls) -> Path:
        """Get primary prompts directory from environment or use default."""
        return Path(os.getenv("ORAC_DEFAULT_PROMPTS_DIR", cls.PACKAGE_DIR / "prompts"))

    @classmethod
    def get_prompts_dirs(cls, project_dir: Optional[Path] = None) -> list[Path]:
        """Get all prompts directories in search order (highest priority first).

        Search order:
        1. Project prompts (.orac/prompts/)
        2. User prompts (~/.config/orac/prompts/)
        3. Package prompts (orac/prompts/)
        """
        dirs = []
        # Project directory (highest priority)
        if project_dir:
            project_prompts = project_dir / ".orac" / "prompts"
        else:
            project_prompts = Path.cwd() / ".orac" / "prompts"
        if project_prompts.exists():
            dirs.append(project_prompts)
        # User directory
        user_prompts = cls._USER_CONFIG_DIR / "prompts"
        if user_prompts.exists():
            dirs.append(user_prompts)
        # Package directory (always included)
        dirs.append(cls.get_prompts_dir())
        return dirs

    @classmethod
    def get_flows_dir(cls) -> Path:
        """Get primary flows directory from environment or use default."""
        return Path(os.getenv("ORAC_DEFAULT_FLOWS_DIR", cls.PACKAGE_DIR / "flows"))

    @classmethod
    def get_flows_dirs(cls, project_dir: Optional[Path] = None) -> list[Path]:
        """Get all flows directories in search order (highest priority first)."""
        dirs = []
        if project_dir:
            project_flows = project_dir / ".orac" / "flows"
        else:
            project_flows = Path.cwd() / ".orac" / "flows"
        if project_flows.exists():
            dirs.append(project_flows)
        user_flows = cls._USER_CONFIG_DIR / "flows"
        if user_flows.exists():
            dirs.append(user_flows)
        dirs.append(cls.get_flows_dir())
        return dirs

    @classmethod
    def get_skills_dir(cls) -> Path:
        """Get primary skills directory from environment or use default."""
        return Path(os.getenv("ORAC_DEFAULT_SKILLS_DIR", cls.PACKAGE_DIR / "skills"))

    @classmethod
    def get_skills_dirs(cls, project_dir: Optional[Path] = None) -> list[Path]:
        """Get all skills directories in search order (highest priority first)."""
        dirs = []
        if project_dir:
            project_skills = project_dir / ".orac" / "skills"
        else:
            project_skills = Path.cwd() / ".orac" / "skills"
        if project_skills.exists():
            dirs.append(project_skills)
        user_skills = cls._USER_CONFIG_DIR / "skills"
        if user_skills.exists():
            dirs.append(user_skills)
        dirs.append(cls.get_skills_dir())
        return dirs

    @classmethod
    def get_agents_dir(cls) -> Path:
        """Get primary agents directory from environment or use default."""
        return Path(os.getenv("ORAC_DEFAULT_AGENTS_DIR", cls.PACKAGE_DIR / "agents"))

    @classmethod
    def get_agents_dirs(cls, project_dir: Optional[Path] = None) -> list[Path]:
        """Get all agents directories in search order (highest priority first)."""
        dirs = []
        if project_dir:
            project_agents = project_dir / ".orac" / "agents"
        else:
            project_agents = Path.cwd() / ".orac" / "agents"
        if project_agents.exists():
            dirs.append(project_agents)
        user_agents = cls._USER_CONFIG_DIR / "agents"
        if user_agents.exists():
            dirs.append(user_agents)
        dirs.append(cls.get_agents_dir())
        return dirs

    @classmethod
    def get_teams_dir(cls) -> Path:
        """Get primary teams directory from environment or use default."""
        return Path(os.getenv("ORAC_DEFAULT_TEAMS_DIR", cls.PACKAGE_DIR / "teams"))

    @classmethod
    def get_teams_dirs(cls, project_dir: Optional[Path] = None) -> list[Path]:
        """Get all teams directories in search order (highest priority first)."""
        dirs = []
        if project_dir:
            project_teams = project_dir / ".orac" / "teams"
        else:
            project_teams = Path.cwd() / ".orac" / "teams"
        if project_teams.exists():
            dirs.append(project_teams)
        user_teams = cls._USER_CONFIG_DIR / "teams"
        if user_teams.exists():
            dirs.append(user_teams)
        dirs.append(cls.get_teams_dir())
        return dirs

    @classmethod
    def find_resource(
        cls,
        name: str,
        resource_type: str,
        project_dir: Optional[Path] = None
    ) -> Optional[Path]:
        """Find a resource file by name, searching all directories.

        Args:
            name: Resource name (without .yaml extension)
            resource_type: One of 'prompts', 'flows', 'skills', 'agents'
            project_dir: Optional project directory to search

        Returns:
            Path to the resource file, or None if not found
        """
        dirs_method = {
            'prompts': cls.get_prompts_dirs,
            'flows': cls.get_flows_dirs,
            'skills': cls.get_skills_dirs,
            'agents': cls.get_agents_dirs,
        }.get(resource_type)

        if not dirs_method:
            return None

        for directory in dirs_method(project_dir):
            for ext in ['.yaml', '.yml']:
                path = directory / f"{name}{ext}"
                if path.exists():
                    return path
        return None

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


class ConfigLoader:
    """Loads and merges configuration from multiple sources.

    Configuration sources (highest to lowest priority):
    1. Runtime overrides (passed to methods)
    2. Project config (./.orac/config.yaml)
    3. User config (~/.config/orac/config.yaml)
    4. Provider defaults
    """

    _USER_CONFIG_PATH = Path.home() / ".config" / "orac" / "config.yaml"
    _PROJECT_CONFIG_NAME = Path(".orac") / "config.yaml"

    def __init__(self, project_dir: Optional[Path] = None):
        """Initialize ConfigLoader.

        Args:
            project_dir: Project directory to search for .orac/config.yaml.
                        If None, uses current working directory.
        """
        self._project_dir = Path(project_dir) if project_dir else Path.cwd()
        self._user_config: Dict[str, Any] = {}
        self._project_config: Dict[str, Any] = {}
        self._merged_config: Dict[str, Any] = {}
        self._load_configs()

    def _load_configs(self) -> None:
        """Load configuration from all sources and merge them."""
        # Load user config
        self._user_config = self._load_yaml(self._USER_CONFIG_PATH)

        # Load project config
        project_config_path = self._project_dir / self._PROJECT_CONFIG_NAME
        self._project_config = self._load_yaml(project_config_path)

        # Merge: user config is base, project config overrides
        self._merged_config = self._deep_merge(
            self._user_config,
            self._project_config
        )

    def _load_yaml(self, path: Path) -> Dict[str, Any]:
        """Load YAML file, returning empty dict if not found."""
        if not path.exists():
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two dictionaries, with override taking precedence."""
        result = deepcopy(base)
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = deepcopy(value)
        return result

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value.

        Args:
            key: Configuration key (e.g., 'provider', 'model', 'api_key_env')
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        return self._merged_config.get(key, default)

    def get_provider(self) -> Optional[Provider]:
        """Get the configured provider."""
        provider_str = self.get('provider')
        if provider_str:
            try:
                return Provider(provider_str)
            except ValueError:
                return None
        return None

    def get_model(self) -> Optional[str]:
        """Get the configured model name."""
        return self.get('model') or self.get('model_name')

    def get_api_key_env(self) -> Optional[str]:
        """Get the configured API key environment variable name."""
        return self.get('api_key_env')

    def get_base_url(self) -> Optional[str]:
        """Get the configured base URL."""
        return self.get('base_url')

    def get_generation_config(self) -> Dict[str, Any]:
        """Get generation config settings."""
        return self.get('generation_config', {})

    def resolve_with_overrides(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key_env: Optional[str] = None,
        base_url: Optional[str] = None,
        generation_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Resolve configuration with runtime overrides.

        Args:
            provider: Runtime provider override
            model: Runtime model override
            api_key_env: Runtime api_key_env override
            base_url: Runtime base_url override
            generation_config: Runtime generation_config override

        Returns:
            Fully resolved configuration dict
        """
        result = deepcopy(self._merged_config)

        # Apply runtime overrides (highest priority)
        if provider is not None:
            result['provider'] = provider
        if model is not None:
            result['model'] = model
        if api_key_env is not None:
            result['api_key_env'] = api_key_env
        if base_url is not None:
            result['base_url'] = base_url
        if generation_config is not None:
            result['generation_config'] = self._deep_merge(
                result.get('generation_config', {}),
                generation_config
            )

        # Fill in provider defaults for missing values
        provider_enum = None
        if result.get('provider'):
            try:
                provider_enum = Provider(result['provider'])
            except ValueError:
                pass

        if provider_enum and provider_enum in _PROVIDER_DEFAULTS:
            defaults = _PROVIDER_DEFAULTS[provider_enum]
            if not result.get('base_url'):
                result['base_url'] = defaults.get('base_url')
            if not result.get('api_key_env'):
                result['api_key_env'] = defaults.get('key_env')

        # Fill in global default model if not set
        if not result.get('model'):
            result['model'] = Config.get_default_model_name()

        return result

    def save_user_config(self, config: Dict[str, Any]) -> None:
        """Save configuration to user config file.

        Args:
            config: Configuration dict to save
        """
        self._USER_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(self._USER_CONFIG_PATH, 'w', encoding='utf-8') as f:
            yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)
        # Reload configs
        self._load_configs()

    def save_project_config(self, config: Dict[str, Any]) -> None:
        """Save configuration to project config file.

        Args:
            config: Configuration dict to save
        """
        project_config_path = self._project_dir / self._PROJECT_CONFIG_NAME
        project_config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(project_config_path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False)
        # Reload configs
        self._load_configs()

    @property
    def user_config_path(self) -> Path:
        """Get the user config file path."""
        return self._USER_CONFIG_PATH

    @property
    def project_config_path(self) -> Path:
        """Get the project config file path."""
        return self._project_dir / self._PROJECT_CONFIG_NAME

    @property
    def has_user_config(self) -> bool:
        """Check if user config file exists."""
        return self._USER_CONFIG_PATH.exists()

    @property
    def has_project_config(self) -> bool:
        """Check if project config file exists."""
        return (self._project_dir / self._PROJECT_CONFIG_NAME).exists()
