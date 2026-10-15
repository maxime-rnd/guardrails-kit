"""Helpers for optional OpenAI SDK integration."""

from __future__ import annotations

import asyncio
import inspect
import os
import re
from pathlib import Path
from typing import Any, Callable

from ..exceptions import ConfigError


def load_project_env() -> None:
    """Load the nearest .env from the current working directory, if present."""
    env_path = next(
        (
            candidate / ".env"
            for candidate in (Path.cwd(), *Path.cwd().parents)
            if (candidate / ".env").is_file()
        ),
        None,
    )
    if env_path is None:
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        # Keep basic KEY=value .env files usable in an existing environment
        # before the newly declared python-dotenv dependency is installed.
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()
            key, separator, value = line.partition("=")
            key = key.strip()
            if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                continue
            if key in os.environ:
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            elif " #" in value:
                value = value.split(" #", 1)[0].rstrip()
            os.environ[key] = value
    else:
        # Keep variables already supplied by the process environment authoritative.
        load_dotenv(env_path, override=False)


def create_openai_client(client: Any | None = None) -> Any:
    """Return an injected client or construct the sync OpenAI client."""
    if client is not None:
        return client
    load_project_env()
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise ConfigError(
            "OpenAI-backed components require the openai package; install the project dependencies."
        ) from exc
    try:
        return OpenAI()
    except Exception as exc:
        raise ConfigError(
            "Could not initialize the OpenAI client. Set OPENAI_API_KEY or pass openai_client."
        ) from exc


def call_sync(method: Callable[..., Any], **kwargs: Any) -> Any:
    """Call a synchronous SDK method, rejecting async clients on the sync API."""
    if inspect.iscoroutinefunction(method):
        raise RuntimeError(
            "An async OpenAI client was supplied; use avalidate_input/output()."
        )
    result = method(**kwargs)
    if inspect.isawaitable(result):
        close = getattr(result, "close", None)
        if close is not None:
            close()
        raise RuntimeError(
            "An async OpenAI client was supplied; use avalidate_input/output()."
        )
    return result


async def call_async(method: Callable[..., Any], **kwargs: Any) -> Any:
    """Call an async SDK method directly or move a sync method to a worker thread."""
    if inspect.iscoroutinefunction(method):
        return await method(**kwargs)
    return await asyncio.to_thread(method, **kwargs)


def response_value(value: Any, key: str) -> Any:
    """Read a field from either an SDK response object or a mapping fake."""
    if isinstance(value, dict):
        return value[key]
    return getattr(value, key)
