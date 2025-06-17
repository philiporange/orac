# client.py
"""
Low-level LLM client helper that now talks through the official
OpenAI Python SDK, targeting Google's OpenAI-compatible endpoint.
The public function name and signature stay the same so llm.py
and cli.py work without changes.
"""

from __future__ import annotations

import os
import base64
from typing import List, Dict, Optional, Any
from loguru import logger
from openai import OpenAI

# ---------------------------------------------------------------------#
# Constants                                                            #
# ---------------------------------------------------------------------#
from orac.config import Config, Provider, _PROVIDER_DEFAULTS

DEFAULT_MODEL_NAME = Config.DEFAULT_MODEL_NAME


# ---------------------------------------------------------------------#
# Helpers                                                              #
# ---------------------------------------------------------------------#
def _get_client(
    provider: Provider, *, api_key: Optional[str] = None, base_url: Optional[str] = None
) -> OpenAI:
    """Instantiate an OpenAI-compatible client for *provider*."""
    defaults = _PROVIDER_DEFAULTS.get(provider, {})
    base_url = base_url or defaults.get("base_url")
    key_env = defaults.get("key_env", "OPENAI_API_KEY")

    api_key = api_key or os.getenv(key_env)
    if not api_key:
        raise ValueError(
            f"No API key found for provider '{provider.value}'. "
            f"Export {key_env}=… or pass --api-key/ api_key='…'"
        )
    if provider is Provider.CUSTOM and not base_url:
        raise ValueError("CUSTOM provider selected – you must also supply --base-url")

    logger.debug(
        f"Creating OpenAI client for provider '{provider.value}' at {base_url}"
    )
    return OpenAI(api_key=api_key, base_url=base_url)


def _encode_file_to_base64(file_path: str) -> str:
    """Encode a file to base64 string."""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _get_mime_type(file_path: str) -> str:
    """Get MIME type based on file extension."""
    ext = file_path.lower().split(".")[-1]
    mime_types = {
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
    }
    return mime_types.get(ext, "application/octet-stream")


def _gai_to_openai_messages(
    history: List[Dict[str, Any]],
    system_prompt: Optional[str],
    file_paths: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Translate the project's message format ({role,text/parts}) into
    OpenAI's {role,content} list with file attachments.
    """
    msgs: List[Dict[str, Any]] = []
    if system_prompt:
        msgs.append({"role": "system", "content": system_prompt})

    for i, msg in enumerate(history):
        role = msg.get("role")
        if role not in ("user", "model"):
            raise ValueError(
                f"Invalid role '{role}' at message {i}; expected 'user' or 'model'."
            )
        text = msg.get("text")
        parts = msg.get("parts")
        if text is None and parts:
            text = "\n".join(map(str, parts))
        if text is None:
            raise ValueError(f"Message {i} is empty.")

        # For the last user message, add files if provided
        if role == "user" and i == len(history) - 1 and file_paths:
            content = [{"type": "text", "text": text}]
            for file_path in file_paths:
                base64_data = _encode_file_to_base64(file_path)
                mime_type = _get_mime_type(file_path)
                data_url = f"data:{mime_type};base64,{base64_data}"
                filename = os.path.basename(file_path)

                # For images, use image_url type; for other files, include as text
                if mime_type.startswith("image/"):
                    content.append(
                        {"type": "image_url", "image_url": {"url": data_url}}
                    )
                else:
                    # For non-image files, include filename and indicate it's attached
                    content.append(
                        {
                            "type": "text",
                            "text": (
                                f"\n\n[File attached: {filename}]\n"
                                f"Content: {data_url}"
                            ),
                        }
                    )
            msgs.append({"role": "user", "content": content})
        else:
            msgs.append(
                {"role": "user" if role == "user" else "assistant", "content": text}
            )
    return msgs


def call_api(
    provider: Provider,
    *,
    message_history: List[Dict[str, Any]],
    file_paths: Optional[List[str]] = None,
    system_prompt: Optional[str] = None,
    model_name: str = DEFAULT_MODEL_NAME,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    generation_config: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Call LLM API
    Supports:
      • chat history + system prompt
      • generation_config passthrough (temperature, max_tokens, etc.)
      • optional file upload (images/docs) via base64 encoding
      • returns `str` with the model's top choice
    """
    client = _get_client(provider, api_key=api_key, base_url=base_url)

    # -----------------------------------------------------------------#
    # Build messages with file attachments                            #
    # -----------------------------------------------------------------#
    if file_paths:
        logger.info(f"Encoding {len(file_paths)} file(s) as base64…")
        for path in file_paths:
            logger.debug(f"Encoding {path} as base64 data")

    messages = _gai_to_openai_messages(message_history, system_prompt, file_paths)
    logger.debug(f"Sending {len(messages)} messages to LLM via OpenAI")

    # -----------------------------------------------------------------#
    # Build request                                                    #
    # -----------------------------------------------------------------#
    req: Dict[str, Any] = {
        "model": model_name,
        "messages": messages,
    }
    if generation_config:
        req.update(generation_config)

    # -----------------------------------------------------------------#
    # Call API                                                         #
    # -----------------------------------------------------------------#
    logger.info(f"Calling model '{model_name}'")
    try:
        response = client.chat.completions.create(**req)
    except Exception as e:
        logger.error(f"LLM API call failed: {e}")
        raise

    # -----------------------------------------------------------------#
    # Return text                                                      #
    # -----------------------------------------------------------------#
    choice = response.choices[0]
    content = getattr(choice.message, "content", "")
    logger.info("LLM completion successful")
    return content
