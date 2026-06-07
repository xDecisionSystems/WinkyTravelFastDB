from __future__ import annotations

from pathlib import Path


def resolve_log_file(root_dir: str, relative_path: str) -> Path:
    if not relative_path.strip():
        raise ValueError("path is required")
    if Path(relative_path).is_absolute():
        raise ValueError("absolute paths are not allowed")

    root = Path(root_dir).resolve()
    requested = (root / relative_path).resolve()

    # Block directory traversal outside the configured log root.
    if root != requested and root not in requested.parents:
        raise ValueError("path must stay under DEV_LOG_ROOT_DIR")

    return requested


def read_log_tail(file_path: Path, max_bytes: int, max_lines: int) -> tuple[str, bool]:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be > 0")
    if max_lines <= 0:
        raise ValueError("max_lines must be > 0")

    with file_path.open("rb") as handle:
        handle.seek(0, 2)
        total_size = handle.tell()
        seek_from = max(total_size - max_bytes, 0)
        handle.seek(seek_from)
        data = handle.read()

    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    truncated = total_size > max_bytes or len(lines) > max_lines
    if len(lines) > max_lines:
        lines = lines[-max_lines:]

    return "\n".join(lines), truncated
