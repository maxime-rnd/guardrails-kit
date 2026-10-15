"""Local, regex-based detection and redaction of common PII and credentials."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...config import TransformConfig
from .base import TransformOperation, parse_transform_params


RedactionType = Literal["email", "api_token", "bearer_token", "person_name"]

_DEFAULT_PATTERNS: dict[str, str] = {
    "email": r"(?P<value>[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)",
    "bearer_token": r"(?i:Bearer\s+)(?P<value>[A-Za-z0-9._~+/-]+=*)",
    "api_token": r"(?P<value>\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,})\b)",
    # TODO: Replace this contextual name heuristic with a local NER model.
    "person_name": (
        r"(?i:my name is|i am|i'm|je m'appelle|mon nom est)\s+"
        r"(?P<value>[A-ZÀ-ÖØ-Þ][^\W\d_]+(?:[-'][A-ZÀ-ÖØ-Þ]?[^\W\d_]+)?"
        r"(?:\s+[A-ZÀ-ÖØ-Þ][^\W\d_]+){0,2})"
    ),
}


class PIIRedactionParams(BaseModel):
    """Parameters for the ``pii_redaction`` transform."""

    model_config = ConfigDict(extra="forbid")

    redact: list[RedactionType] = Field(
        default_factory=lambda: ["email", "api_token", "bearer_token", "person_name"],
        min_length=1,
    )

    @field_validator("redact")
    @classmethod
    def _redaction_types_are_unique(
        cls, values: list[RedactionType]
    ) -> list[RedactionType]:
        if len(set(values)) != len(values):
            raise ValueError("redact entries must be unique")
        return values


class PIIRedactorCore:
    """Regex-based text transformer. Names need a future NER model for recall."""

    def __init__(self, params: PIIRedactionParams) -> None:
        self.params = params
        self._patterns = {
            kind: re.compile(_DEFAULT_PATTERNS[kind]) for kind in params.redact
        }

    def transform(self, value: str) -> str:
        """Return redacted text directly for use as a pipeline transform."""
        if not isinstance(value, str):
            raise TypeError(f"PII redaction expects str, got {type(value).__name__}.")
        redacted = value
        for kind, pattern in self._patterns.items():
            matches = list(pattern.finditer(redacted))
            for match in reversed(matches):
                group_name = "value" if "value" in pattern.groupindex else None
                start, end = match.span(group_name) if group_name else match.span()
                redacted = redacted[:start] + f"[{kind.upper()}]" + redacted[end:]
        return redacted


class PIIRedactor(TransformOperation):
    """Python component that masks selected PII patterns in text."""

    type_name = "pii_redaction"

    @classmethod
    def from_config(
        cls, config: TransformConfig, *, openai_client: object | None = None
    ) -> PIIRedactor:
        params = parse_transform_params(PIIRedactionParams, config)
        return cls(redact=params.redact)

    def __init__(self, *, redact: list[str] | None = None) -> None:
        super().__init__()
        params = (
            PIIRedactionParams(redact=redact)
            if redact is not None
            else PIIRedactionParams()
        )
        self._core = PIIRedactorCore(params)

    def transform(self, value: str) -> str:
        return self._core.transform(value)
