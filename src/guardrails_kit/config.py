"""YAML configuration loading and schema validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    ValidationError,
    model_validator,
)

from .exceptions import ConfigError
from .models import Phase


class CheckConfig(BaseModel):
    """Configuration of one check implementation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    type: str = Field(min_length=1)
    phase: Phase
    enabled: StrictBool = True
    params: dict[str, Any] = Field(default_factory=dict)


class TransformConfig(BaseModel):
    """Configuration passed to a transform implementation factory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    type: str = Field(min_length=1)
    phase: Phase
    enabled: StrictBool = True
    params: dict[str, Any] = Field(default_factory=dict)


class PipelineStepConfig(BaseModel):
    """One ordered transform or check in a pipeline."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    kind: Literal["transform", "check"]
    type: str = Field(min_length=1)
    phase: Phase
    input: str = Field(min_length=1)
    output: str | None = None
    enabled: StrictBool = True
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_shape(self) -> PipelineStepConfig:
        if self.kind == "transform" and not self.output:
            raise ValueError(
                f"transform step {self.name!r} must declare an output name"
            )
        if self.kind == "check" and self.output is not None:
            raise ValueError(f"check step {self.name!r} cannot declare an output")
        if self.output is not None and (not self.output.strip() or "." in self.output):
            raise ValueError("output must be a non-empty name without dots")
        if self.input != "input" and not self.input.startswith(("input.", "outputs.")):
            raise ValueError("input must start with 'input.' or 'outputs.'")
        if self.input.endswith(".") or ".." in self.input:
            raise ValueError("input reference contains an empty path segment")
        if "field" in self.params:
            raise ValueError("use the step's input reference instead of params.field")
        return self


class PipelineConfig(BaseModel):
    """Version 2 ordered pipeline configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[2]
    steps: list[PipelineStepConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_names_and_references(self) -> PipelineConfig:
        names: set[str] = set()
        outputs: dict[str, tuple[Phase, bool]] = {}
        output_names: set[str] = set()
        for step in self.steps:
            if step.name in names:
                raise ValueError(f"duplicate step name {step.name!r}")
            names.add(step.name)
            if step.input.startswith("outputs."):
                output_name = step.input.split(".", 2)[1]
                if output_name not in outputs:
                    raise ValueError(
                        f"step {step.name!r} references output {output_name!r} "
                        "before it is produced"
                    )
                output_phase, output_enabled = outputs[output_name]
                if not output_enabled:
                    raise ValueError(
                        f"step {step.name!r} depends on disabled output {output_name!r}"
                    )
                if output_phase is not step.phase:
                    raise ValueError(
                        f"step {step.name!r} must reference an output from the same phase"
                    )
            if step.output is not None:
                if step.output in output_names:
                    raise ValueError(f"duplicate output name {step.output!r}")
                output_names.add(step.output)
                outputs[step.output] = (step.phase, step.enabled)
        return self


def format_validation_error(exc: ValidationError) -> str:
    """Render a Pydantic error as a compact, human-readable string."""
    parts = []
    for err in exc.errors(include_url=False, include_context=False):
        loc = ".".join(str(p) for p in err["loc"]) or "<root>"
        parts.append(f"{loc}: {err['msg']}")
    return "; ".join(parts)


def parse_config(raw: Any) -> PipelineConfig:
    """Validate a version 2 pipeline configuration mapping."""
    if not isinstance(raw, dict):
        raise ConfigError("The configuration root must be a mapping.")
    try:
        return PipelineConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(
            f"Invalid configuration: {format_validation_error(exc)}"
        ) from exc


def load_config(path: str | Path) -> PipelineConfig:
    """Read and validate a version 2 pipeline YAML file."""
    file_path = Path(path)
    try:
        text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(
            f"Cannot read configuration file {str(file_path)!r}: {exc}"
        ) from exc
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {str(file_path)!r}: {exc}") from exc
    return parse_config(raw)
