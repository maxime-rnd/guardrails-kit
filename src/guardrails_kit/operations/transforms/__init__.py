"""Built-in transforms and their YAML type registry."""

from __future__ import annotations

from typing import Any

from ...config import TransformConfig
from ...exceptions import ConfigError
from ...utils.openai import create_openai_client
from .base import TransformOperation, parse_transform_params
from .llm_extractor import LLMExtractor, LLMExtractorParams
from .pii_redactor import PIIRedactionParams, PIIRedactor

_TRANSFORM_TYPES: dict[str, type[TransformOperation]] = {}


def register_transform_type(
    transform_cls: type[TransformOperation],
) -> type[TransformOperation]:
    """Register a transform implementation for YAML configuration."""
    name = transform_cls.type_name
    if name in _TRANSFORM_TYPES and _TRANSFORM_TYPES[name] is not transform_cls:
        raise ValueError(f"Transform type {name!r} is already registered.")
    _TRANSFORM_TYPES[name] = transform_cls
    return transform_cls


def create_transform(
    config: TransformConfig, *, openai_client: Any | None = None
) -> TransformOperation:
    """Instantiate a configured transform, validating it during setup."""
    transform_cls = _TRANSFORM_TYPES.get(config.type)
    if transform_cls is None:
        known = ", ".join(sorted(_TRANSFORM_TYPES))
        raise ConfigError(
            f"Transform {config.name!r}: unknown type {config.type!r} "
            f"(known types: {known})."
        )
    try:
        if config.type == LLMExtractor.type_name:
            if openai_client is None:
                # Disabled steps are still constructed for introspection. Avoid
                # requiring OpenAI credentials until such a step is enabled.
                openai_client = (
                    object() if not config.enabled else create_openai_client()
                )
        return transform_cls.from_config(config, openai_client=openai_client)
    except NotImplementedError as exc:
        raise ConfigError(
            f"Transform {config.name!r} ({config.type}) cannot be built from YAML."
        ) from exc


register_transform_type(PIIRedactor)
register_transform_type(LLMExtractor)

__all__ = [
    "LLMExtractor",
    "LLMExtractorParams",
    "PIIRedactionParams",
    "PIIRedactor",
    "TransformOperation",
    "parse_transform_params",
    "create_transform",
    "register_transform_type",
]
