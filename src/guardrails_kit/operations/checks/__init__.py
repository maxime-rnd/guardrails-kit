"""Built-in checks and their YAML type registry."""

from __future__ import annotations

from ...config import CheckConfig
from ...exceptions import ConfigError
from .base import CheckOperation
from .condition_check import ConditionCheck, ConditionParams
from .embedding_similarity_check import (
    EmbeddingSimilarityCheck,
    EmbeddingSimilarityParams,
)
from .pydantic_check import PydanticCheck
from .regex_check import RegexCheck

_CHECK_TYPES: dict[str, type[CheckOperation]] = {}


def register_check_type(check_cls: type[CheckOperation]) -> type[CheckOperation]:
    name = check_cls.type_name
    if name in _CHECK_TYPES and _CHECK_TYPES[name] is not check_cls:
        raise ValueError(f"Check type {name!r} is already registered.")
    _CHECK_TYPES[name] = check_cls
    return check_cls


def create_check(
    config: CheckConfig, *, openai_client: object | None = None
) -> CheckOperation:
    check_cls = _CHECK_TYPES.get(config.type)
    if check_cls is None:
        known = ", ".join(sorted(_CHECK_TYPES))
        raise ConfigError(
            f"Check {config.name!r}: unknown type {config.type!r} (known types: {known})."
        )
    if config.type == "embedding_similarity":
        return check_cls.from_config(config, openai_client=openai_client)  # type: ignore[call-arg]
    return check_cls.from_config(config)


for _check in (PydanticCheck, RegexCheck, EmbeddingSimilarityCheck, ConditionCheck):
    register_check_type(_check)

__all__ = [
    "CheckOperation",
    "ConditionCheck",
    "ConditionParams",
    "EmbeddingSimilarityCheck",
    "EmbeddingSimilarityParams",
    "PydanticCheck",
    "RegexCheck",
    "create_check",
    "register_check_type",
]
