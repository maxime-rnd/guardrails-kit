"""Shared contract for pipeline steps."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Self

from pydantic import BaseModel, ConfigDict, model_validator

from ..models import CheckResult, Phase, TransformResult


class Step(BaseModel, ABC):
    """Frozen common model and execution contract for pipeline steps."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    name: str
    source: str
    using: Any
    phase: Phase = Phase.INPUT
    enabled: bool = True

    operation_method: ClassVar[str]

    @model_validator(mode="after")
    def _validate_operation(self) -> Self:
        method = getattr(self.using, self.operation_method, None)
        if not callable(method):
            raise TypeError(
                f"Step {self.name!r} requires an operation with a callable "
                f"{self.operation_method}() method."
            )
        return self

    @abstractmethod
    def run(self, value: Any) -> TransformResult | CheckResult:
        """Run the operation synchronously and return its pipeline result."""

    @abstractmethod
    async def arun(self, value: Any) -> TransformResult | CheckResult:
        """Run the operation asynchronously and return its pipeline result."""

    @abstractmethod
    def error_result(
        self, exc: Exception, duration_ms: float
    ) -> TransformResult | CheckResult:
        """Build a result representing an operation error."""


def operation_type(operation: Any) -> str:
    """Return a stable snake_case name for a configured operation."""
    name = getattr(operation, "type_name", None) or getattr(operation, "__name__", None)
    if name is None:
        name = type(operation).__name__
    return re.sub(r"(?<!^)(?=[A-Z])", "_", str(name)).lower()
