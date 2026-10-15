"""Public data structures for transform and check results."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from enum import Enum, StrEnum
from typing import Annotated, Any, Iterator, Literal, TypeVar, overload

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    kind: Literal["transform"] = "transform"
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
    kind: Literal["check"] = "check"
    name: str
    check_type: str
    phase: Phase | None = None
    status: CheckStatus
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    duration_ms: float | None = None


StepResult = Annotated[
    TransformResult | CheckResult,
    Field(discriminator="kind"),
]


class StepResults(BaseModel):
    """Pipeline step results in execution order, addressable by index or name."""

    model_config = ConfigDict(frozen=True)

    items: tuple[StepResult, ...] = ()

    @model_validator(mode="after")
    def _names_are_unique(self) -> StepResults:
        names = [result.name for result in self.items]
        if len(names) != len(set(names)):
            raise ValueError("step result names must be unique")
        return self

    @overload
    def __getitem__(self, key: int) -> StepResult: ...

    @overload
    def __getitem__(self, key: str) -> StepResult: ...

    @overload
    def __getitem__(self, key: slice) -> tuple[StepResult, ...]: ...

    def __getitem__(
        self, key: int | slice | str
    ) -> StepResult | tuple[StepResult, ...]:
        if isinstance(key, str):
            for result in self.items:
                if result.name == key:
                    return result
            raise KeyError(key)
        return self.items[key]

    def __iter__(self) -> Iterator[StepResult]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)


class GuardrailsReport(BaseModel):
    """Ordered step results and named transform outputs for one pipeline phase."""

    model_config = ConfigDict(frozen=True)
    phase: Phase
    outputs: dict[str, Any] = Field(default_factory=dict)
    step_results: StepResults = Field(default_factory=StepResults)

    @property
    def transforms(self) -> tuple[TransformResult, ...]:
        """Transform results in pipeline order, for kind-specific access."""
        return tuple(
            result
            for result in self.step_results
            if isinstance(result, TransformResult)
        )

    @property
    def checks(self) -> tuple[CheckResult, ...]:
        """Check results in pipeline order, for kind-specific access."""
        return tuple(
            result for result in self.step_results if isinstance(result, CheckResult)
        )

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
        return any(
            isinstance(item, CheckResult) and item.status is CheckStatus.FAIL
            for item in self.step_results
        )

    @property
    def has_errors(self) -> bool:
        return any(
            (isinstance(item, CheckResult) and item.status is CheckStatus.ERROR)
            or (
                isinstance(item, TransformResult)
                and item.status is TransformStatus.ERROR
            )
            for item in self.step_results
        )

    @property
    def failures(self) -> tuple[CheckResult, ...]:
        return tuple(
            item
            for item in self.step_results
            if isinstance(item, CheckResult) and item.status is CheckStatus.FAIL
        )

    @property
    def errors(self) -> tuple[TransformResult | CheckResult, ...]:
        return tuple(
            item
            for item in self.step_results
            if (isinstance(item, CheckResult) and item.status is CheckStatus.ERROR)
            or (
                isinstance(item, TransformResult)
                and item.status is TransformStatus.ERROR
            )
        )

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
            "step_results": [
                jsonable(item.model_dump(mode="python")) for item in self.step_results
            ],
        }
