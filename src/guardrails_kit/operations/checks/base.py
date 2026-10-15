"""Base class shared by every check."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Self, TypeVar

from pydantic import BaseModel, ValidationError

from ...config import CheckConfig, format_validation_error
from ...exceptions import ConfigError
from ...models import CheckResult, CheckStatus

P = TypeVar("P", bound=BaseModel)


def parse_params(params_model: type[P], config: CheckConfig) -> P:
    """Validate ``config.params`` against a check-specific Pydantic model.

    Raises:
        ConfigError: with the check name in the message if params are invalid.
    """
    try:
        return params_model.model_validate(config.params)
    except ValidationError as exc:
        raise ConfigError(
            f"Check {config.name!r} ({config.type}): invalid params: "
            f"{format_validation_error(exc)}"
        ) from exc


class CheckOperation(ABC):
    """A single validation check.

    To add a new check type: subclass ``CheckOperation``, set ``type_name``, implement
    ``from_config`` (validate params, fail early with ``ConfigError``) and
    ``check`` (return a ``CheckResult``), then call ``register_check_type``.

    A check decides its domain verdict (pass, fail, or skipped) because that
    verdict depends on the rule being evaluated. The enclosing ``Check`` step
    adds pipeline metadata and measures execution time; raised exceptions become
    technical errors there.
    """

    type_name: ClassVar[str]

    def __init__(self, name: str) -> None:
        self.name = name

    @classmethod
    def from_config(cls, config: CheckConfig) -> Self:
        """Build a YAML-configured check; Python-only checks can omit this factory."""
        raise NotImplementedError(f"{cls.__name__} cannot be built from configuration.")

    @abstractmethod
    def check(self, data: Any) -> CheckResult:
        """Check ``data`` and return a structured result.

        Checks should report successfully evaluated violations as ``fail``.
        Exceptions and other technical inability to evaluate are reported as
        ``error`` by the engine. Checks may return ``error`` when no
        structure can be produced; they do not use ``fail`` for that outcome.
        """

    async def acheck(self, data: Any) -> CheckResult:
        """Async variant of :meth:`check`.

        The default implementation runs the synchronous ``check`` in a
        worker thread so it never blocks the event loop. Checks doing real
        async I/O (e.g. an LLM call) should override this method.
        """
        return await asyncio.to_thread(self.check, data)

    def _result(
        self,
        status: CheckStatus,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> CheckResult:
        """Build a result pre-filled with this check's identity."""
        return CheckResult(
            name=self.name,
            check_type=self.type_name,
            status=status,
            message=message,
            details=details or {},
        )
