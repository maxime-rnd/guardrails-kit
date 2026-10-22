"""Check validating data against a Pydantic model referenced from YAML."""

from __future__ import annotations

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, ValidationError

from ...config import CheckConfig
from ...models import CheckResult, CheckStatus
from ...utils.model_loader import resolve_model
from .base import CheckOperation, parse_params


class PydanticParams(BaseModel):
    """Parameters of a ``pydantic`` check."""

    model_config = ConfigDict(extra="forbid")

    model: str | dict[str, Any]  # import path or inline JSON Schema


class PydanticCheck(CheckOperation):
    """Validates data with ``Model.model_validate`` (or ``model_validate_json``).

    The model class is imported once, when the check is built.
    """

    type_name = "pydantic"

    def __init__(self, name: str, model: type[BaseModel], model_source: str) -> None:
        super().__init__(name)
        self.model = model
        self.model_source = model_source

    @classmethod
    def from_config(cls, config: CheckConfig) -> Self:
        params = parse_params(PydanticParams, config)
        model_source = (
            params.model if isinstance(params.model, str) else "inline JSON Schema"
        )
        try:
            model = resolve_model(params.model)
        except Exception as exc:
            raise type(exc)(f"Check {config.name!r}: {exc}") from exc
        return cls(config.name, model, model_source)

    def check(self, data: Any) -> CheckResult:
        try:
            if isinstance(data, (str, bytes, bytearray)):
                self.model.model_validate_json(data)
            else:
                self.model.model_validate(data)
        except ValidationError as exc:
            # Keep only JSON-safe, non-sensitive fields (no raw input values).
            errors = [
                {"loc": [str(p) for p in e["loc"]], "type": e["type"], "msg": e["msg"]}
                for e in exc.errors(include_url=False, include_context=False)
            ]
            fields = sorted({".".join(error["loc"]) or "<root>" for error in errors})
            field_list = ", ".join(fields)
            return self._result(
                CheckStatus.FAIL,
                f"Data does not match {self.model.__name__}: {len(errors)} validation error(s) "
                f"in {field_list}.",
                {"model": self.model_source, "errors": errors},
            )
        return self._result(
            CheckStatus.PASS,
            f"Data matches {self.model.__name__}.",
            {"model": self.model_source},
        )
