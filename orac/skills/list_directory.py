"""List directory contents with optional glob filtering and recursive traversal.

Returns a formatted listing showing type (DIR/FILE), size, and name for each
entry. Supports glob patterns and recursive mode for deep exploration.
"""

from pathlib import Path
from typing import Dict, Any, Union


def _format_size(size_bytes: int) -> str:
    """Format byte count as human-readable size."""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:>6.0f}{unit}" if unit == "B" else f"{size_bytes:>6.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:>6.1f}TB"


def _entry_line(entry: Path, base: Path) -> str:
    """Format a single directory entry as 'TYPE SIZE NAME'."""
    rel = entry.relative_to(base)
    if entry.is_dir():
        return f"DIR  {'':>7} {rel}/"
    try:
        size = _format_size(entry.stat().st_size)
    except OSError:
        size = "     ?"
    return f"FILE {size} {rel}"


def execute(inputs: Dict[str, Any]) -> Union[str, Dict[str, Any]]:
    """List directory contents.

    Args:
        inputs: Dictionary with 'path' (str), optional 'pattern' (str),
                and optional 'recursive' (bool).

    Returns:
        Dict with 'listing' (formatted text) and 'count' on success,
        or a string error message on failure.
    """
    dir_path = Path(inputs["path"]).expanduser().resolve()
    pattern = inputs.get("pattern", None)
    recursive = inputs.get("recursive", False)

    if not dir_path.exists():
        return f"Error: Path not found: {dir_path}"

    if not dir_path.is_dir():
        return f"Error: Not a directory: {dir_path}"

    try:
        if pattern:
            glob_pattern = f"**/{pattern}" if recursive else pattern
            entries = sorted(dir_path.glob(glob_pattern))
        elif recursive:
            entries = sorted(dir_path.rglob("*"))
        else:
            entries = sorted(dir_path.iterdir())
    except OSError as e:
        return f"Error listing directory: {e}"

    lines = [_entry_line(e, dir_path) for e in entries]

    if not lines:
        listing = "(empty directory)" if not pattern else f"(no entries matching '{pattern}')"
    else:
        listing = "\n".join(lines)

    return {
        "listing": listing,
        "count": len(lines),
    }
