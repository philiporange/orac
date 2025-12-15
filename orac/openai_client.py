# openai_client.py
"""
Low-level LLM client helper using ProviderRegistry for multi-provider support.
Uses explicit provider registry instead of automatic environment access.
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
from orac.config import Config, Provider
from .providers import ProviderRegistry

# Note: DEFAULT_MODEL_NAME now comes from Config.get_default_model_name()


# ---------------------------------------------------------------------#
# Helpers                                                              #
# ---------------------------------------------------------------------#


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
        "txt": "text/plain",
        "md": "text/markdown",
        "py": "text/plain",
        "js": "text/plain",
        "json": "application/json",
        "csv": "text/csv",
        "html": "text/html",
        "xml": "text/xml",
    }
    return mime_types.get(ext, "text/plain")


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
                # Note: Google hack to send pdfs as image_url type
                elif mime_type == "application/pdf":
                    print("Warning: Sending PDF as image_url type is a Google hack.")
                    content.append(
                        {"type": "image_url", "image_url": {"url": data_url}}
                    )
                else:
                    # For non-image files, use image_url type (Google API requirement)
                    logger.debug(f"Sending {filename} ({mime_type}) as image_url type (Google API workaround)")
                    content.append(
                        {"type": "image_url", "image_url": {"url": data_url}}
                    )
            msgs.append({"role": "user", "content": content})
        else:
            msgs.append(
                {"role": "user" if role == "user" else "assistant", "content": text}
            )
    return msgs


def call_api(
    provider_registry: ProviderRegistry,
    provider: Optional[Provider] = None,  # Use default if None
    *,
    message_history: List[Dict[str, Any]],
    file_paths: Optional[List[str]] = None,
    system_prompt: Optional[str] = None,
    model_name: Optional[str] = None,  # Use provider's model if None
    generation_config: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Call LLM API using provider registry.
    Supports:
      • chat history + system prompt
      • generation_config passthrough (temperature, max_tokens, etc.)
      • optional file upload (images/docs) via base64 encoding
      • returns `str` with the model's top choice
    """
    client = provider_registry.get_client(provider)
    
    # Get model name from registry if not specified
    resolved_model_name = model_name or provider_registry.get_model_name(provider)

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
        "model": resolved_model_name,
        "messages": messages,
    }
    if generation_config:
        req.update(generation_config)

    # -----------------------------------------------------------------#
    # Call API                                                         #
    # -----------------------------------------------------------------#
    logger.info(f"Calling model '{resolved_model_name}' via provider '{provider or provider_registry.get_default_provider()}'")
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
