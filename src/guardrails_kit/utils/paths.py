"""Helpers for resolving dotted paths through common Python data objects."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


MISSING = object()


def resolve_path(data: Any, path: str | None) -> Any:
    """Resolve a dotted path in mappings, sequences, or object attributes.

    Returns :data:`MISSING` when a key, index, or attribute does not exist.
    Passing ``None`` as the path returns ``data`` unchanged.
    """
    if path is None:
        return data
    current = data
    for part in path.split(".") if path else ():
        if isinstance(current, Mapping):
            if part not in current:
                return MISSING
            current = current[part]
        elif isinstance(current, (list, tuple)):
            if not part.isdigit() or int(part) >= len(current):
                return MISSING
            current = current[int(part)]
        else:
            try:
                current = getattr(current, part)
            except AttributeError:
                return MISSING
    return current
