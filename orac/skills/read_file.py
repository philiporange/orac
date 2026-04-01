"""Read a text file and return its contents.

Detects binary files via null-byte heuristic and known binary extensions,
returning an error message directing the caller to use transcribe_file
for non-textual content. Large files are truncated to max_chars with a
notice appended.
"""

from pathlib import Path
from typing import Dict, Any, Union

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp",
    ".ico", ".svg", ".heic", ".heif",
    ".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".wma",
    ".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar", ".xz",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".dat",
    ".pyc", ".pyo", ".class", ".o", ".obj",
    ".db", ".sqlite", ".sqlite3",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
}

SAMPLE_SIZE = 8192  # bytes to check for null bytes


def _is_binary(path: Path) -> bool:
    """Detect binary files using extension check and null-byte heuristic."""
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    try:
        with open(path, "rb") as f:
            sample = f.read(SAMPLE_SIZE)
        return b"\x00" in sample
    except OSError:
        return False


def execute(inputs: Dict[str, Any]) -> Union[str, Dict[str, Any]]:
    """Read a file and return its text content.

    Args:
        inputs: Dictionary with 'path' (str) and optional 'max_chars' (int).

    Returns:
        Dict with 'content', 'path', and 'size_bytes' on success,
        or a string error message on failure.
    """
    file_path = Path(inputs["path"]).expanduser().resolve()
    max_chars = int(inputs.get("max_chars", 50000))

    if not file_path.exists():
        return f"Error: File not found: {file_path}"

    if not file_path.is_file():
        return f"Error: Not a file: {file_path}"

    if _is_binary(file_path):
        return (
            f"Error: '{file_path.name}' appears to be a binary file. "
            f"Use prompt:transcribe_file with file_path=\"{file_path}\" "
            f"to extract its content via LLM transcription."
        )

    size_bytes = file_path.stat().st_size

    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return f"Error reading file: {e}"

    truncated = False
    if len(text) > max_chars:
        text = text[:max_chars]
        truncated = True

    content = text
    if truncated:
        content += f"\n\n[TRUNCATED: showing first {max_chars} of {size_bytes} bytes]"

    return {
        "content": content,
        "path": str(file_path),
        "size_bytes": size_bytes,
    }
