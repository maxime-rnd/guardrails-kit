"""Transform pipeline step implementation."""

from __future__ import annotations

import asyncio
import time
from typing import Any, ClassVar

from ..models import Phase, TransformResult, TransformStatus
from ..operations.transforms.base import TransformOperation
from .base import Step, operation_type


class TransformStep(Step):
    """Apply ``using`` to ``source`` and store its value in ``target``."""

    target: str
    using: TransformOperation

    operation_method: ClassVar[str] = "transform"

    def _result_for(self, value: Any, duration_ms: float) -> TransformResult:
        return TransformResult(
            name=self.name,
            transform_type=operation_type(self.using),
            phase=self.phase,
            status=TransformStatus.SUCCESS,
            output_name=self.target,
            value=value,
            message=f"Transformed {type(value).__name__} into outputs.{self.target}.",
            details={"output_type": type(value).__name__},
            duration_ms=duration_ms,
        )

    def run(self, value: Any) -> TransformResult:
        started = time.perf_counter()
        produced = self.using.transform(value)
        elapsed_ms = (time.perf_counter() - started) * 1000
        return self._result_for(produced, elapsed_ms)

    async def arun(self, value: Any) -> TransformResult:
        method = getattr(self.using, "atransform", None)
        if not callable(method):
            return await asyncio.to_thread(self.run, value)
        started = time.perf_counter()
        produced = await method(value)
        elapsed_ms = (time.perf_counter() - started) * 1000
        return self._result_for(produced, elapsed_ms)

    def error_result(self, exc: Exception, duration_ms: float) -> TransformResult:
        return TransformResult(
            name=self.name,
            transform_type=operation_type(self.using),
            phase=self.phase,
            status=TransformStatus.ERROR,
            output_name=self.target,
            value=None,
            message=f"Step raised {type(exc).__name__}: {exc}",
            details={"exception_type": type(exc).__name__},
            duration_ms=duration_ms,
        )
