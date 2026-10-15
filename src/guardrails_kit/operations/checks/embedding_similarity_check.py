"""Few-shot semantic similarity check using OpenAI embeddings."""

from __future__ import annotations

import math
import os
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...config import CheckConfig
from ...models import CheckResult, CheckStatus
from .base import CheckOperation, parse_params
from ...utils.paths import MISSING, resolve_path
from ...utils.openai import (
    call_async,
    call_sync,
    create_openai_client,
    load_project_env,
    response_value,
)


class EmbeddingSimilarityParams(BaseModel):
    """Parameters for an ``embedding_similarity`` check."""

    model_config = ConfigDict(extra="forbid")

    examples: list[str] = Field(min_length=1)
    threshold: float = Field(ge=0.0, le=1.0)
    field: str | None = None
    model: str | None = None
    dimensions: int | None = Field(default=None, gt=0)
    on_missing: Literal["fail", "skip"] = "fail"

    @field_validator("examples")
    @classmethod
    def _examples_are_nonempty(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("examples must not contain empty strings")
        return values

    @field_validator("model")
    @classmethod
    def _model_is_nonempty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("model must not be empty")
        return value


def _embedding(response: Any, index: int) -> list[float]:
    rows = response_value(response, "data")
    row = rows[index]
    return [float(value) for value in response_value(row, "embedding")]


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("OpenAI returned embeddings with inconsistent dimensions.")
    denominator = math.sqrt(sum(v * v for v in left) * sum(v * v for v in right))
    if denominator == 0:
        raise ValueError("OpenAI returned a zero-length embedding vector.")
    return sum(a * b for a, b in zip(left, right)) / denominator


class EmbeddingSimilarityCheck(CheckOperation):
    """Pass when input text is sufficiently similar to at least one example."""

    type_name = "embedding_similarity"

    def __init__(
        self,
        name: str,
        params: EmbeddingSimilarityParams,
        openai_client: Any | None = None,
    ) -> None:
        super().__init__(name)
        self.params = params
        load_project_env()
        self.model = (
            params.model
            or os.getenv("OPENAI_EMBEDDING_MODEL")
            or "text-embedding-3-small"
        )
        self.client = create_openai_client(openai_client)

    @classmethod
    def from_config(
        cls, config: CheckConfig, *, openai_client: Any | None = None
    ) -> Self:
        return cls(
            config.name,
            parse_params(EmbeddingSimilarityParams, config),
            openai_client,
        )

    def _text(self, data: Any) -> str | CheckResult:
        value = resolve_path(data, self.params.field)
        if value is MISSING:
            status = (
                CheckStatus.SKIPPED
                if self.params.on_missing == "skip"
                else CheckStatus.FAIL
            )
            return self._result(
                status,
                f"Field {self.params.field!r} is absent.",
                {"field": self.params.field},
            )
        if not isinstance(value, str) or not value.strip():
            return self._result(
                CheckStatus.FAIL,
                "Input value must be a non-empty string.",
                {"field": self.params.field, "actual_type": type(value).__name__},
            )
        return value

    def _request(self, text: str) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": self.model,
            "input": [text, *self.params.examples],
            "encoding_format": "float",
        }
        if self.params.dimensions is not None:
            request["dimensions"] = self.params.dimensions
        return request

    def _result_for(self, response: Any) -> CheckResult:
        input_vector = _embedding(response, 0)
        similarities = [
            _cosine(input_vector, _embedding(response, index))
            for index in range(1, len(self.params.examples) + 1)
        ]
        best_index = max(range(len(similarities)), key=similarities.__getitem__)
        score = similarities[best_index]
        details = {
            "model": self.model,
            "field": self.params.field,
            "threshold": self.params.threshold,
            "similarity": score,
            "matched_example_index": best_index,
        }
        best_example = best_index + 1
        if score >= self.params.threshold:
            message = (
                f"Similarity {score:.4f} meets threshold {self.params.threshold:.4f}; "
                f"closest match is example {best_example}."
            )
            return self._result(CheckStatus.PASS, message, details)
        message = (
            f"Similarity {score:.4f} is below threshold {self.params.threshold:.4f}; "
            f"closest match is example {best_example}."
        )
        return self._result(CheckStatus.FAIL, message, details)

    def check(self, data: Any) -> CheckResult:
        text = self._text(data)
        if isinstance(text, CheckResult):
            return text
        response = call_sync(self.client.embeddings.create, **self._request(text))
        return self._result_for(response)

    async def acheck(self, data: Any) -> CheckResult:
        text = self._text(data)
        if isinstance(text, CheckResult):
            return text
        response = await call_async(
            self.client.embeddings.create, **self._request(text)
        )
        return self._result_for(response)
