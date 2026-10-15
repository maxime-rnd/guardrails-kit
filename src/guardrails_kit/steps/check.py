"""Check pipeline step implementation."""

from __future__ import annotations

import asyncio
import time
from typing import Any, ClassVar

from ..operations.checks.base import CheckOperation
from ..models import CheckResult, CheckStatus
from .base import Step, operation_type


class CheckStep(Step):
    """Evaluate ``using`` against ``source`` without changing the value."""

    using: CheckOperation

    operation_method: ClassVar[str] = "check"

    def _result_for(self, checked: CheckResult, duration_ms: float) -> CheckResult:
        if not isinstance(checked, CheckResult):
            raise TypeError("A check must return CheckResult.")
        return checked.model_copy(
            update={
                "name": self.name,
                "check_type": operation_type(self.using),
                "phase": self.phase,
                "details": {"input": self.source, **checked.details},
                "duration_ms": duration_ms,
            }
        )

    def run(self, value: Any) -> CheckResult:
        started = time.perf_counter()
        checked = self.using.check(value)
        elapsed_ms = (time.perf_counter() - started) * 1000
        return self._result_for(checked, elapsed_ms)

    async def arun(self, value: Any) -> CheckResult:
        method = getattr(self.using, "acheck", None)
        if not callable(method):
            return await asyncio.to_thread(self.run, value)
        started = time.perf_counter()
        checked = await method(value)
        elapsed_ms = (time.perf_counter() - started) * 1000
        return self._result_for(checked, elapsed_ms)

    def error_result(self, exc: Exception, duration_ms: float) -> CheckResult:
        return CheckResult(
            name=self.name,
            check_type=operation_type(self.using),
            phase=self.phase,
            status=CheckStatus.ERROR,
            message=f"Step raised {type(exc).__name__}: {exc}",
            details={"exception_type": type(exc).__name__},
            duration_ms=duration_ms,
        )
