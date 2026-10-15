"""Check validating a field against a regular expression."""

from __future__ import annotations

import re
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, field_validator

from ...config import CheckConfig
from ...models import CheckResult, CheckStatus
from ...utils.paths import MISSING, resolve_path
from .base import CheckOperation, parse_params

_FLAGS = {
    "ignorecase": re.IGNORECASE,
    "multiline": re.MULTILINE,
    "dotall": re.DOTALL,
    "ascii": re.ASCII,
}


class RegexParams(BaseModel):
    """Parameters of a ``regex`` check."""

    model_config = ConfigDict(extra="forbid")

    pattern: str
    # Dotted path to the field to check ("user.email", "items.0.name").
    # If omitted, the whole payload must be a string.
    field: str | None = None
    # search: match anywhere; match: from the start; fullmatch: whole value.
    mode: Literal["search", "match", "fullmatch"] = "search"
    # If true, the check fails when the pattern IS found (forbidden pattern).
    forbid: bool = False
    flags: list[Literal["ignorecase", "multiline", "dotall", "ascii"]] = []
    # What to do when the field is absent from the data.
    on_missing: Literal["fail", "skip"] = "fail"

    @field_validator("pattern")
    @classmethod
    def _pattern_compiles(cls, value: str) -> str:
        try:
            re.compile(value)
        except re.error as exc:
            raise ValueError(f"invalid regular expression: {exc}") from exc
        return value


class RegexCheck(CheckOperation):
    """Checks a string field against a regular expression."""

    type_name = "regex"

    def __init__(self, name: str, params: RegexParams) -> None:
        super().__init__(name)
        self.params = params
        flags = 0
        for flag in params.flags:
            flags |= _FLAGS[flag]
        # Compiled once at load time.
        self._compiled = re.compile(params.pattern, flags)

    @classmethod
    def from_config(cls, config: CheckConfig) -> Self:
        return cls(config.name, parse_params(RegexParams, config))

    def check(self, data: Any) -> CheckResult:
        p = self.params
        details: dict[str, Any] = {
            "field": p.field,
            "pattern": p.pattern,
            "mode": p.mode,
        }
        field_name = p.field or "<input>"

        value = resolve_path(data, p.field)
        if value is MISSING:
            if p.on_missing == "skip":
                return self._result(
                    CheckStatus.SKIPPED,
                    f"Field {p.field!r} is absent; regex check skipped.",
                    details,
                )
            return self._result(
                CheckStatus.FAIL, f"Required field {p.field!r} is absent.", details
            )
        if not isinstance(value, str):
            details["actual_type"] = type(value).__name__
            return self._result(
                CheckStatus.FAIL,
                f"Field {field_name!r} must be a string for regex {p.pattern!r} (got {type(value).__name__}).",
                details,
            )

        matched = getattr(self._compiled, p.mode)(value) is not None
        if p.forbid:
            if matched:
                return self._result(
                    CheckStatus.FAIL,
                    f"Field {field_name!r} contains forbidden pattern {p.pattern!r} (mode={p.mode}).",
                    details,
                )
            return self._result(
                CheckStatus.PASS,
                f"Field {field_name!r} does not contain forbidden pattern {p.pattern!r} (mode={p.mode}).",
                details,
            )
        if matched:
            return self._result(
                CheckStatus.PASS,
                f"Field {field_name!r} matches regex {p.pattern!r} (mode={p.mode}).",
                details,
            )
        return self._result(
            CheckStatus.FAIL,
            f"Field {field_name!r} does not match regex {p.pattern!r} (mode={p.mode}).",
            details,
        )
