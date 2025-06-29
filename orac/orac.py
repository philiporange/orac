"""
LLM wrapper that loads YAML prompt-specs, resolves parameters, handles
**local *and* remote files**, and finally calls the OpenAI-compatible
chat-completion endpoint.
"""

from __future__ import annotations

import os
import glob
import json
import yaml
import urllib.request
from urllib.parse import urlparse
from pathlib import Path
from string import Template
from copy import deepcopy
from typing import List, Dict, Any, Optional
from loguru import logger

from orac.client import call_api
from orac.config import Config, Provider, LLM_PROVIDER
from orac.conversation_db import ConversationDB


# --------------------------------------------------------------------------- #
# Constants & helpers                                                         #
# --------------------------------------------------------------------------- #
DEFAULT_PROMPTS_DIR = Config.DEFAULT_PROMPTS_DIR
DEFAULT_CONFIG_FILE = Config.DEFAULT_CONFIG_FILE

_RESERVED_CLIENT_KWARGS = Config.RESERVED_CLIENT_KWARGS
SUPPORTED_TYPES = Config.SUPPORTED_TYPES
_DOWNLOAD_DIR = Config.DOWNLOAD_DIR


def _deep_merge_dicts(base: dict, extra: dict) -> dict:
    """Recursively merge two dictionaries. 'extra' values override 'base' values."""
    merged = base.copy()
    for key, value in extra.items():
        if isinstance(value, dict) and key in merged and isinstance(merged[key], dict):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _merge_generation_config(
    base: Optional[Dict[str, Any]], extra: Optional[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """Shallow-merge two generation_config dicts, giving *extra* precedence."""
    if base is None and extra is None:
        return None
    merged: Dict[str, Any] = {}
    if base:
        merged.update(base)
    if extra:
        merged.update(extra)
    return merged or None


def _inject_response_format(gen_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Translate legacy structured-output keys (response_mime_type / response_schema)
    into the official OpenAI `response_format` object – unless already present.
    """
    cfg = deepcopy(gen_cfg) if gen_cfg else {}
    if "response_format" in cfg:
        return cfg

    mime = cfg.pop("response_mime_type", None)
    schema = cfg.pop("response_schema", None)

    if schema is not None:
        cfg["response_format"] = {
            "type": "json_schema",
            "json_schema": {"schema": schema},
        }
    elif mime == "application/json":
        cfg["response_format"] = {"type": "json_object"}

    return cfg


# --------------------------------------------------------------------------- #
# Remote-file utilities                                                       #
# --------------------------------------------------------------------------- #
def _is_http_url(s: str) -> bool:
    try:
        scheme = urlparse(s).scheme.lower()
        return scheme in {"http", "https"}
    except Exception:  # pragma: no cover
        return False


def _download_remote_file(url: str) -> str:
    """
    Download *url* to the project-wide cache dir and return the local path.
    The same filename is reused if the file already exists.
    """
    if not _is_http_url(url):
        raise ValueError(f"Invalid remote URL: {url}")

    # Build deterministic filename so duplicates are cached
    name = Path(urlparse(url).path).name or "remote_file"
    target = _DOWNLOAD_DIR / name
    if target.exists():
        logger.debug(f"[cache] Re-using downloaded file: {target}")
        return str(target)

    logger.info(f"Downloading remote file: {url}")
    try:
        with urllib.request.urlopen(url) as resp, open(target, "wb") as fh:
            fh.write(resp.read())
    except Exception as exc:
        raise RuntimeError(f"Failed to download {url}: {exc}") from exc

    logger.debug(f"Saved remote file to: {target}")
    return str(target)


# --------------------------------------------------------------------------- #
# LLMWrapper                                                                  #
# --------------------------------------------------------------------------- #
class Orac:
    """
    High-level helper that:
      • loads YAML prompt specs,
      • validates & substitutes parameters,
      • handles **local + remote files**,
      • and finally calls the LLM via `client.call_api()`.
    """

    # --------------------------- initialisation --------------------------- #
    def __init__(
        self,
        prompt_name: str,
        prompts_dir: Optional[str] = None,
        base_config_file: Optional[str] = None,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        generation_config: Optional[Dict[str, Any]] = None,
        verbose: bool = False,
        files: Optional[List[str]] = None,
        file_urls: Optional[List[str]] = None,
        provider: Optional[str | Provider] = None,
        base_url: Optional[str] = None,
        use_conversation: Optional[bool] = None,
        conversation_id: Optional[str] = None,
        auto_save: bool = True,
        max_history: Optional[int] = None,
    ):
        # Detect “direct file” mode (prompt_name points to a real .yaml file)
        pn_path = Path(prompt_name)
        if pn_path.suffix.lower() in {".yaml", ".yml"}:
            if not pn_path.is_file():
                raise FileNotFoundError(f"Prompt YAML file not found: {pn_path}")
            self.yaml_file_path = str(pn_path.expanduser().resolve())
            self.prompt_name = pn_path.stem
            self.prompts_root_dir = str(pn_path.parent)
        else:
            self.prompt_name = prompt_name
            self.prompts_root_dir = prompts_dir or DEFAULT_PROMPTS_DIR
            self.yaml_file_path = None  # resolved later

        self.verbose = verbose
        self.files = files or []
        self.file_urls = file_urls or []
        
        # Store conversation constructor params (will be processed after config loading)
        self._init_use_conversation = use_conversation
        self._init_conversation_id = conversation_id
        self._init_auto_save = auto_save
        self._init_max_history = max_history

        # Resolve provider
        self.provider: Provider | None = None
        if provider:
            self.provider = (
                Provider(provider) if isinstance(provider, str) else provider
            )
        elif os.getenv("ORAC_LLM_PROVIDER"):
            self.provider = Provider(os.getenv("ORAC_LLM_PROVIDER"))
        elif LLM_PROVIDER:
            self.provider = LLM_PROVIDER

        if self.provider is None:
            raise ValueError(
                "Select an LLM provider first: export "
                "ORAC_LLM_PROVIDER=openai|google|anthropic|azure|custom "
                "or pass provider= parameter."
            )

        logger.debug(
            f"Initialising Orac for prompt: {self.prompt_name} "
            f"(provider: {self.provider.value})"
        )

        # 1. Load base config
        config_path = base_config_file or DEFAULT_CONFIG_FILE
        base_config = self._load_yaml_file(config_path, silent_not_found=True)

        # 2. Load prompt-specific config
        if self.yaml_file_path is None:
            self.yaml_file_path = os.path.join(
                self.prompts_root_dir, f"{self.prompt_name}.yaml"
            )
        prompt_config = self._load_yaml_file(self.yaml_file_path)
        self.yaml_base_dir = os.path.dirname(os.path.abspath(self.yaml_file_path))

        # 3. Deep merge
        self.config = _deep_merge_dicts(base_config, prompt_config)
        self._parse_and_validate_config()

        # -------------------------- conversation setup ------------------------ #
        # Runtime param takes precedence, then YAML config, then global default
        if self._init_use_conversation is not None:
            # Explicit runtime parameter provided
            self.use_conversation = self._init_use_conversation
        elif self.yaml_conversation:
            # YAML config specifies conversation mode
            self.use_conversation = True
        else:
            # Use global default
            self.use_conversation = Config.DEFAULT_CONVERSATION_MODE
        self.conversation_id = self._init_conversation_id
        self.auto_save = self._init_auto_save
        self.max_history = self._init_max_history or Config.MAX_CONVERSATION_HISTORY
        self._conversation_db: Optional[ConversationDB] = None
        
        # Initialize conversation if needed
        if self.use_conversation:
            self._init_conversation()

        # -------------------------- prompt setup --------------------------- #
        # Set prompt template based on final conversation mode determination
        if self.use_conversation:
            # In conversation mode, always use the standard message template
            self.prompt_template_str = "${message}"
        else:
            # Normal mode requires explicit prompt
            if not self.yaml_prompt or not isinstance(self.yaml_prompt, str):
                raise ValueError("Config must contain a top-level 'prompt' string.")
            self.prompt_template_str = self.yaml_prompt

        # -------------------------- client-kwargs -------------------------- #
        client_kwargs: Dict[str, Any] = {}

        client_kwargs["model_name"] = model_name or self.config.get("model_name")
        client_kwargs["api_key"] = api_key or self.config.get("api_key")
        client_kwargs["base_url"] = base_url or self.config.get("base_url")

        # generation_config
        base_cfg = deepcopy(self.config.get("generation_config")) or {}
        extra_cfg = deepcopy(generation_config) or {}

        if self.config.get("response_mime_type"):
            base_cfg["response_mime_type"] = self.config.get("response_mime_type")
        if self.config.get("response_schema"):
            base_cfg["response_schema"] = self.config.get("response_schema")

        merged_cfg = _merge_generation_config(base_cfg, extra_cfg)
        if merged_cfg:
            client_kwargs["generation_config"] = merged_cfg

        # Store: exclude provider to avoid duplicate arg in call_api
        self.client_kwargs = {k: v for k, v in client_kwargs.items() if v is not None}

    # ------------------------- YAML helpers ------------------------------- #
    def _load_yaml_file(self, path: str | Path, silent_not_found: bool = False) -> dict:
        """Helper to load a YAML file and return a dict."""
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            if not isinstance(data, dict):
                raise ValueError(f"YAML file at {path} must be a mapping (dictionary).")
            return data
        except FileNotFoundError:
            if silent_not_found:
                logger.debug(f"Config file not found, skipping: {path}")
                return {}
            raise

    def _parse_and_validate_config(self):
        """Read & validate keys from the merged self.config dictionary."""
        data = self.config

        # conversation settings (parse early as it affects prompt handling)
        self.yaml_conversation = data.get("conversation", False)
        if not isinstance(self.yaml_conversation, bool):
            raise ValueError("'conversation' must be a boolean when provided.")
        
        # For conversation prompts, having a fallback prompt is actually useful
        # for when someone explicitly disables conversation mode at runtime

        # Store YAML prompt for later processing (after conversation mode is determined)
        self.yaml_prompt = data.get("prompt")

        self.system_prompt_template_str = data.get("system_prompt")
        if self.system_prompt_template_str is not None and not isinstance(
            self.system_prompt_template_str, str
        ):
            raise ValueError("'system_prompt' must be a string when provided.")

        # files & parameters
        self.yaml_files_spec = data.get("files", [])
        if not isinstance(self.yaml_files_spec, list):
            raise ValueError("'files' must be a list when provided.")

        yaml_url_single = data.get("file_url")
        yaml_url_multi = data.get("file_urls", [])
        if yaml_url_single:
            yaml_url_multi = [yaml_url_single] + (yaml_url_multi or [])
        if not isinstance(yaml_url_multi, list):
            raise ValueError("'file_urls' must be a list when provided.")
        self.yaml_file_urls_spec = yaml_url_multi

        self.yaml_require_file = data.get("require_file", False)
        if not isinstance(self.yaml_require_file, bool):
            raise ValueError("'require_file' must be a boolean when provided.")

        self.parameters_spec = data.get("parameters", [])
        if not isinstance(self.parameters_spec, list):
            raise ValueError("'parameters' must be a list when provided.")

        # validate parameters
        for param in self.parameters_spec:
            if not isinstance(param, dict) or "name" not in param:
                raise ValueError(
                    "Each parameter spec must be a dict containing a 'name' key."
                )
            name = param["name"]
            if name in _RESERVED_CLIENT_KWARGS:
                raise ValueError(
                    f"Parameter '{name}' conflicts with a reserved config key."
                )
            ptype = param.get("type")
            if ptype and ptype not in SUPPORTED_TYPES:
                raise ValueError(
                    f"Unsupported parameter type '{ptype}' for '{name}'. "
                    f"Supported types: {list(SUPPORTED_TYPES)}"
                )

    # ------------------- parameter helpers ------------------------------ #
    def _convert_type(self, value: Any, t: str, name: str) -> Any:
        """Coerce value into type *t*."""
        if t not in SUPPORTED_TYPES:
            return value
        typ = SUPPORTED_TYPES[t]

        try:
            if t in ("bool", "boolean"):
                if isinstance(value, str):
                    return value.lower() in ("true", "1", "yes", "on", "y")
                return bool(value)
            if t in ("list", "array"):
                if isinstance(value, str):
                    return [v.strip() for v in value.split(",") if v.strip()]
                if isinstance(value, list):
                    return value
                return [value]
            return typ(value)
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"Cannot convert parameter '{name}' to {t}: {exc}"
            ) from exc

    def _validate_required_optional(self, spec: Dict[str, Any]) -> tuple[bool, bool]:
        has_default = "default" in spec
        is_required = spec.get("required", not has_default)
        return is_required, not is_required or has_default

    def _resolve_parameters(self, **kwargs_params) -> Dict[str, Any]:
        resolved: Dict[str, Any] = {}
        for spec in self.parameters_spec:
            name = spec["name"]
            t = spec.get("type", "str")
            req, _ = self._validate_required_optional(spec)

            if name in kwargs_params:
                val = kwargs_params[name]
                resolved[name] = self._convert_type(val, t, name) if t else val
            elif "default" in spec:
                default_val = spec["default"]
                resolved[name] = self._convert_type(default_val, t, name)
            elif req:
                raise ValueError(
                    (
                        f"Required parameter '{name}' for prompt "
                        f"'{self.prompt_name}' was not provided."
                    )
                )
            else:
                resolved[name] = None
        return resolved

    # ---------------- template & file utilities ------------------------- #
    @staticmethod
    def _format_string(
        template: Optional[str], params: Dict[str, Any]
    ) -> Optional[str]:
        if template is None:
            return None
        try:
            return Template(template).substitute(params)
        except KeyError as exc:
            raise KeyError(f"Missing parameter {exc} in template.") from exc

    def _resolve_local_file_paths(self) -> List[str]:
        """Expand glob patterns from YAML to absolute file paths."""
        resolved: List[str] = []
        for pattern in self.yaml_files_spec:
            if _is_http_url(pattern):
                continue
            abs_pattern = os.path.join(self.yaml_base_dir, pattern)
            for path in glob.glob(abs_pattern):
                if os.path.isfile(path):
                    resolved.append(os.path.abspath(path))
        return resolved

    def _resolve_remote_urls(self) -> List[str]:
        """Collect remote URLs from YAML + constructor."""
        urls = [u for u in self.yaml_files_spec if _is_http_url(u)]
        urls.extend(self.yaml_file_urls_spec)
        urls.extend(self.file_urls or [])
        # De-duplicate
        seen: set[str] = set()
        unique_urls: List[str] = []
        for u in urls:
            if u not in seen:
                unique_urls.append(u)
                seen.add(u)
        return unique_urls

    # ------------------- conversation management ------------------------- #
    def _init_conversation(self):
        """Initialize conversation database and ID."""
        if self._conversation_db is None:
            self._conversation_db = ConversationDB(Config.CONVERSATION_DB)
        
        if self.conversation_id is None:
            # Try to reuse the most recent conversation for this prompt
            conversations = self._conversation_db.list_conversations()
            recent_conv = None
            for conv in conversations:
                if conv['prompt_name'] == self.prompt_name:
                    recent_conv = conv
                    break  # list_conversations() returns newest first
            
            if recent_conv:
                self.conversation_id = recent_conv['id']
                logger.debug(f"Reusing recent conversation: {self.conversation_id}")
            else:
                # No existing conversation for this prompt, create new one
                self.conversation_id = self._conversation_db.create_conversation(
                    prompt_name=self.prompt_name
                )
                logger.debug(f"Created new conversation: {self.conversation_id}")
        elif not self._conversation_db.conversation_exists(self.conversation_id):
            # Create conversation if it doesn't exist
            self._conversation_db.create_conversation(
                conversation_id=self.conversation_id,
                prompt_name=self.prompt_name
            )

    # --------------------------- completion ------------------------------ #
    def completion(
        self,
        message_history: Optional[List[Dict[str, Any]]] = None,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        generation_config: Optional[Dict[str, Any]] = None,
        file_urls: Optional[List[str]] = None,
        **kwargs_params,
    ) -> str:
        """
        Execute the prompt and return the model’s response.
        (String for normal prompts, JSON string when JSON/Schema mode.)
        """
        # Resolve parameters & fill templates
        params = self._resolve_parameters(**kwargs_params)
        
        # Format the user prompt
        user_prompt = self._format_string(self.prompt_template_str, params)
            
        system_prompt = self._format_string(self.system_prompt_template_str, params)

        # ----------------------- File handling --------------------------- #
        local_files = self._resolve_local_file_paths()
        local_files.extend(
            os.path.abspath(p) for p in (self.files or []) if p and os.path.isfile(p)
        )

        all_urls = self._resolve_remote_urls()
        if file_urls:
            all_urls.extend(file_urls)
        downloaded_paths = [_download_remote_file(u) for u in all_urls]

        all_files = local_files + downloaded_paths

        if self.yaml_require_file and not all_files:
            raise ValueError(
                (
                    f"Files are required for prompt '{self.prompt_name}' "
                    "but none were supplied."
                )
            )

        # -------------------- Assemble call-kwargs ----------------------- #
        call_kwargs = deepcopy(self.client_kwargs)

        if model_name is not None:
            call_kwargs["model_name"] = model_name
        if api_key is not None:
            call_kwargs["api_key"] = api_key

        base_cfg = deepcopy(call_kwargs.get("generation_config") or {})
        extra_cfg = deepcopy(generation_config) or {}
        merged_cfg = _merge_generation_config(base_cfg, extra_cfg)
        call_kwargs["generation_config"] = _inject_response_format(merged_cfg)

        # Build message history - with conversation support
        api_history: List[Dict[str, Any]] = list(message_history or [])
        
        # Load conversation history if enabled
        if self.use_conversation and self._conversation_db:
            stored_messages = self._conversation_db.get_messages(
                self.conversation_id, limit=self.max_history
            )
            for msg in stored_messages:
                api_history.append({
                    "role": "user" if msg["role"] == "user" else "model",
                    "text": msg["content"]
                })
        
        # Add current user message
        api_history.append({"role": "user", "text": user_prompt})
        
        # Save user message if conversation is enabled
        if self.use_conversation and self.auto_save and self._conversation_db:
            self._conversation_db.add_message(
                self.conversation_id, "user", user_prompt
            )

        # Call the client – pass provider **once**
        result = call_api(
            provider=self.provider,
            message_history=api_history,
            file_paths=all_files,
            system_prompt=system_prompt,
            **call_kwargs,
        )
        
        # Save assistant response if conversation is enabled
        if self.use_conversation and self.auto_save and self._conversation_db:
            self._conversation_db.add_message(
                self.conversation_id, "assistant", result
            )
        
        return result

    def completion_as_json(
        self,
        message_history: Optional[List[Dict[str, Any]]] = None,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        generation_config: Optional[Dict[str, Any]] = None,
        file_urls: Optional[List[str]] = None,
        **kwargs_params,
    ) -> dict:
        """Returns parsed JSON, raises exception if not valid JSON"""
        result = self.completion(
            message_history=message_history,
            model_name=model_name,
            api_key=api_key,
            generation_config=generation_config,
            file_urls=file_urls,
            **kwargs_params,
        )
        return json.loads(result)

    def __call__(
        self,
        message_history: Optional[List[Dict[str, Any]]] = None,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        generation_config: Optional[Dict[str, Any]] = None,
        file_urls: Optional[List[str]] = None,
        force_json: bool = False,
        **kwargs_params,
    ) -> str | dict:
        """
        Sophisticated wrapper around completion that automatically detects and parses JSON responses.
        
        Args:
            force_json: If True, raises an error if response isn't valid JSON
            **kwargs: All other arguments passed to completion()
            
        Returns:
            dict if response is valid JSON, str otherwise
            
        Raises:
            ValueError: If force_json=True and response is not valid JSON
        """
        result = self.completion(
            message_history=message_history,
            model_name=model_name,
            api_key=api_key,
            generation_config=generation_config,
            file_urls=file_urls,
            **kwargs_params,
        )
        
        # Try to parse as JSON
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            if force_json:
                raise ValueError(f"Response is not valid JSON: {result}")
            return result

    # ---------------------- Introspection helpers ----------------------- #
    def get_parameter_info(self) -> List[Dict[str, Any]]:
        """Return structured description of parameters (used by `cli.py --info`)."""
        info: List[Dict[str, Any]] = []
        for spec in self.parameters_spec:
            name = spec["name"]
            ptype = spec.get("type", "string")
            desc = spec.get("description", "")
            has_default = "default" in spec
            default_val = spec.get("default")
            required = spec.get("required", not has_default)
            info.append(
                {
                    "name": name,
                    "type": ptype,
                    "description": desc,
                    "required": bool(required),
                    "has_default": bool(has_default),
                    "default": default_val,
                }
            )
        return info
    
    # ------------------- conversation methods ---------------------------- #
    def reset_conversation(self):
        """Reset the current conversation by deleting all messages."""
        if not self.use_conversation or not self._conversation_db:
            raise ValueError("Conversation mode is not enabled")
        
        if self.conversation_id:
            self._conversation_db.delete_conversation(self.conversation_id)
            # Recreate the conversation
            self._conversation_db.create_conversation(
                conversation_id=self.conversation_id,
                prompt_name=self.prompt_name
            )
            logger.info(f"Reset conversation: {self.conversation_id}")
    
    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Get the conversation history.
        
        Returns:
            List of messages with role and content.
        """
        if not self.use_conversation or not self._conversation_db:
            raise ValueError("Conversation mode is not enabled")
        
        return self._conversation_db.get_messages(self.conversation_id)
    
    def list_conversations(self) -> List[Dict[str, Any]]:
        """List all conversations.
        
        Returns:
            List of conversation metadata.
        """
        if not self._conversation_db:
            self._conversation_db = ConversationDB(Config.CONVERSATION_DB)
        
        return self._conversation_db.list_conversations()
    
    def delete_conversation(self, conversation_id: Optional[str] = None):
        """Delete a conversation.
        
        Args:
            conversation_id: The conversation to delete. Uses current if None.
        """
        if not self._conversation_db:
            self._conversation_db = ConversationDB(Config.CONVERSATION_DB)
        
        target_id = conversation_id or self.conversation_id
        if target_id:
            self._conversation_db.delete_conversation(target_id)
