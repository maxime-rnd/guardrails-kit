"""Simple comparisons for checking values produced by pipeline steps."""

from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from ...config import CheckConfig
from ...models import CheckResult, CheckStatus
from .base import CheckOperation, parse_params


class ConditionParams(BaseModel):
    """Comparison to apply to the value selected by a pipeline input path."""

    model_config = ConfigDict(extra="forbid")

    operator: Literal[
        "equals", "not_equals", "in", "not_in", "gt", "gte", "lt", "lte", "contains"
    ]
    value: Any

    @model_validator(mode="after")
    def _membership_value_is_a_collection(self) -> ConditionParams:
        if self.operator in {"in", "not_in"} and not isinstance(
            self.value, (list, tuple, set, frozenset, str)
        ):
            raise ValueError(
                f"operator {self.operator!r} requires a collection or string"
            )
        return self


class ConditionCheck(CheckOperation):
    """Check a scalar value against a configured comparison."""

    type_name = "condition"

    def __init__(self, name: str, params: ConditionParams) -> None:
        super().__init__(name)
        self.params = params

    @classmethod
    def from_config(cls, config: CheckConfig) -> Self:
        return cls(config.name, parse_params(ConditionParams, config))

    def check(self, data: Any) -> CheckResult:
        p = self.params
        try:
            passed = {
                "equals": lambda: data == p.value,
                "not_equals": lambda: data != p.value,
                "in": lambda: data in p.value,
                "not_in": lambda: data not in p.value,
                "gt": lambda: data > p.value,
                "gte": lambda: data >= p.value,
                "lt": lambda: data < p.value,
                "lte": lambda: data <= p.value,
                "contains": lambda: p.value in data,
            }[p.operator]()
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Cannot apply operator {p.operator!r} to values of type "
                f"{type(data).__name__} and {type(p.value).__name__}."
            ) from exc

        status = CheckStatus.PASS if passed else CheckStatus.FAIL
        relation = "satisfies" if passed else "does not satisfy"
        message = f"Value {relation} condition {p.operator} {p.value!r}."
        return self._result(
            status, message, {"operator": p.operator, "expected": p.value}
        )
