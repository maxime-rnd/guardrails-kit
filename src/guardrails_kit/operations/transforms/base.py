"""Shared contract for operations that produce a transformed value."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Self, TypeVar

from pydantic import BaseModel, ValidationError

from ...config import TransformConfig, format_validation_error
from ...exceptions import ConfigError

ParamsT = TypeVar("ParamsT", bound=BaseModel)


def parse_transform_params(
    params_model: type[ParamsT], config: TransformConfig
) -> ParamsT:
    """Validate transform-specific parameters during configuration loading."""
    try:
        return params_model.model_validate(config.params)
    except ValidationError as exc:
        raise ConfigError(
            f"Transform {config.name!r} ({config.type}): invalid params: "
            f"{format_validation_error(exc)}"
        ) from exc


class TransformOperation(ABC):
    """Base class for reusable synchronous or asynchronous transforms.

    A transform may normalize text, redact data, extract a typed object, or
    otherwise produce the value that downstream steps consume. It returns that
    value directly; the enclosing ``Transform`` step adds execution status and
    pipeline metadata to the ``TransformResult``.
    """

    type_name: ClassVar[str]

    @classmethod
    def from_config(
        cls, config: TransformConfig, *, openai_client: Any | None = None
    ) -> Self:
        """Build a YAML-configured transform; subclasses opt in by overriding."""
        raise NotImplementedError(f"{cls.__name__} cannot be built from configuration.")

    @abstractmethod
    def transform(self, value: Any) -> Any:
        """Return the transformed value, raising when the operation fails."""

    async def atransform(self, value: Any) -> Any:
        """Async counterpart; sync transforms run outside the event loop."""
        return await asyncio.to_thread(self.transform, value)
