"""Typed extraction through OpenAI-compatible chat completions."""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...config import TransformConfig
from ...utils.model_loader import resolve_model
from ...utils.openai import (
    call_async,
    call_sync,
    create_openai_client,
    load_project_env,
    response_value,
)
from .base import TransformOperation, parse_transform_params


class LLMExtractorParams(BaseModel):
    """Parameters for an LLM structured extraction operation."""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1)
    output_model: type[BaseModel] | str | dict[str, Any]
    model: str | None = None
    max_output_tokens: int | None = Field(default=None, gt=0)

    @field_validator("prompt")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value

    @field_validator("output_model")
    @classmethod
    def _output_model_path_is_not_blank(
        cls, value: type[BaseModel] | str | dict[str, Any]
    ) -> type[BaseModel] | str | dict[str, Any]:
        if isinstance(value, str) and not value.strip():
            raise ValueError("output_model path must not be empty")
        return value


class LLMExtractorCore:
    """Transform a Pydantic structure using OpenAI-compatible chat completions."""

    def __init__(
        self, params: LLMExtractorParams, openai_client: Any | None = None
    ) -> None:
        self.params = params
        load_project_env()
        self.model = params.model or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        self.output_model = resolve_model(params.output_model)
        self.output_model.model_json_schema()
        self.client = create_openai_client(openai_client)

    def _request(self, data: Any) -> dict[str, Any]:
        value = data
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"Cannot extract {self.output_model.__name__}: input must be a non-empty string "
                f"(got {type(value).__name__})."
            )
        request: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.params.prompt},
                {"role": "user", "content": value},
            ],
            "response_format": self.output_model,
        }
        if self.params.max_output_tokens is not None:
            request["max_tokens"] = self.params.max_output_tokens
        return request

    def _output_from_response(self, response: Any) -> BaseModel:
        choices = response_value(response, "choices")
        if not choices:
            raise RuntimeError("OpenAI returned no completion choices.")
        message = response_value(choices[0], "message")
        output = response_value(message, "parsed")
        if output is None:
            raise RuntimeError(
                "OpenAI returned no structured output (the response may be a refusal)."
            )
        if isinstance(output, BaseModel):
            return output
        if isinstance(output, dict):
            return self.output_model.model_validate(output)
        else:
            raise TypeError(
                "OpenAI structured output was not a Pydantic model or mapping."
            )

    def transform(self, data: Any) -> BaseModel:
        """Transform and return the typed model directly."""
        request = self._request(data)
        response = call_sync(self.client.chat.completions.parse, **request)
        return self._output_from_response(response)

    async def atransform(self, data: Any) -> BaseModel:
        """Async variant of :meth:`transform`."""
        request = self._request(data)
        response = await call_async(self.client.chat.completions.parse, **request)
        return self._output_from_response(response)


class LLMExtractor(TransformOperation):
    """Python component for extracting a typed structure as a transform."""

    type_name = "llm_extractor"

    @classmethod
    def from_config(
        cls, config: TransformConfig, *, openai_client: Any | None = None
    ) -> LLMExtractor:
        params = parse_transform_params(LLMExtractorParams, config)
        return cls(
            output_model=params.output_model,
            prompt=params.prompt,
            model=params.model,
            max_output_tokens=params.max_output_tokens,
            openai_client=openai_client,
        )

    def __init__(
        self,
        *,
        output_model: type[BaseModel] | str | dict[str, Any],
        prompt: str,
        model: str | None = None,
        max_output_tokens: int | None = None,
        openai_client: Any | None = None,
    ) -> None:
        super().__init__()
        params = LLMExtractorParams(
            output_model=output_model,
            prompt=prompt,
            model=model,
            max_output_tokens=max_output_tokens,
        )
        self._core = LLMExtractorCore(params, openai_client=openai_client)

    def transform(self, value: Any) -> BaseModel:
        return self._core.transform(value)

    async def atransform(self, value: Any) -> BaseModel:
        return await self._core.atransform(value)
