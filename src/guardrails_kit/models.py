"""Public data structures for transform and check results."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from enum import Enum, StrEnum
from typing import Any, TypeVar, overload

from pydantic import BaseModel, ConfigDict, Field

OutputT = TypeVar("OutputT")


class Phase(StrEnum):
    INPUT = "input"
    OUTPUT = "output"


class CheckStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SKIPPED = "skipped"


class TransformStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    SKIPPED = "skipped"


class TransformResult(BaseModel):
    """Execution result for one transform and its named output."""

    model_config = ConfigDict(frozen=True)
    name: str
    transform_type: str
    phase: Phase
    status: TransformStatus
    output_name: str
    value: Any
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float | None = None


class CheckResult(BaseModel):
    """Check result; the pipeline step supplies its phase."""

    model_config = ConfigDict(frozen=True)
    name: str
    check_type: str
    phase: Phase | None = None
    status: CheckStatus
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float | None = None


class GuardrailsReport(BaseModel):
    """Typed transform outputs and check verdicts for one pipeline phase."""

    model_config = ConfigDict(frozen=True)
    phase: Phase
    outputs: dict[str, Any] = Field(default_factory=dict)
    transforms: tuple[TransformResult, ...] = ()
    checks: tuple[CheckResult, ...] = ()

    @overload
    def get_output(self, name: str) -> Any: ...

    @overload
    def get_output(self, name: str, output_type: type[OutputT]) -> OutputT: ...

    def get_output(self, name: str, output_type: type[OutputT] | None = None) -> Any:
        try:
            output = self.outputs[name]
        except KeyError as exc:
            raise KeyError(f"Pipeline output {name!r} was not produced.") from exc
        if output_type is not None and not isinstance(output, output_type):
            raise TypeError(
                f"Pipeline output {name!r} is {type(output).__name__}, "
                f"not {output_type.__name__}."
            )
        return output

    @property
    def passed(self) -> bool:
        return not self.has_failures and not self.has_errors

    @property
    def has_failures(self) -> bool:
        return any(item.status is CheckStatus.FAIL for item in self.checks)

    @property
    def has_errors(self) -> bool:
        return any(item.status is CheckStatus.ERROR for item in self.checks) or any(
            item.status is TransformStatus.ERROR for item in self.transforms
        )

    @property
    def failures(self) -> tuple[CheckResult, ...]:
        return tuple(item for item in self.checks if item.status is CheckStatus.FAIL)

    @property
    def errors(self) -> tuple[TransformResult | CheckResult, ...]:
        transforms = tuple(
            item for item in self.transforms if item.status is TransformStatus.ERROR
        )
        checks = tuple(item for item in self.checks if item.status is CheckStatus.ERROR)
        return transforms + checks

    def to_dict(self) -> dict[str, Any]:
        def jsonable(value: Any) -> Any:
            if isinstance(value, BaseModel):
                return jsonable(value.model_dump(mode="python"))
            if isinstance(value, Enum):
                return value.value
            if is_dataclass(value) and not isinstance(value, type):
                return jsonable(asdict(value))
            if isinstance(value, Mapping):
                return {key: jsonable(item) for key, item in value.items()}
            if isinstance(value, (list, tuple, set, frozenset)):
                return [jsonable(item) for item in value]
            return value

        return {
            "phase": self.phase.value,
            "passed": self.passed,
            "has_failures": self.has_failures,
            "has_errors": self.has_errors,
            "outputs": jsonable(self.outputs),
            "transforms": [
                jsonable(item.model_dump(mode="python")) for item in self.transforms
            ],
            "checks": [
                jsonable(item.model_dump(mode="python")) for item in self.checks
            ],
        }
