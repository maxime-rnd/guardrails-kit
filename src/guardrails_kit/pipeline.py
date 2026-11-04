"""Sequential orchestration for configured transform and check steps."""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .operations.checks import create_check
from .config import (
    CheckConfig,
    PipelineConfig,
    PipelineStepConfig,
    TransformConfig,
    load_config,
    parse_config,
)
from .models import (
    CheckResult,
    GuardrailsReport,
    StepResults,
    TransformResult,
)
from .steps import CheckStep, Step, TransformStep, step_config
from .operations.transforms import create_transform
from .utils.paths import MISSING, resolve_path

logger = logging.getLogger(__name__)


def _required_path(value: Any, path: str) -> Any:
    resolved = resolve_path(value, path)
    if resolved is MISSING:
        raise KeyError(path)
    return resolved


def _resolve_reference(reference: str, data: Any, outputs: dict[str, Any]) -> Any:
    if reference == "input":
        return data

    namespace, path = reference.split(".", 1)
    if namespace == "input":
        return _required_path(data, path)

    output_name, separator, output_path = path.partition(".")
    if output_name not in outputs:
        raise KeyError(f"outputs.{output_name}")
    return _required_path(outputs[output_name], output_path if separator else "")


class Guardrails:
    """Run transforms and checks sequentially, preserving named outputs."""

    def __init__(self, steps: Sequence[Step]) -> None:
        configured: list[tuple[PipelineStepConfig, Step]] = []
        for step in steps:
            if not isinstance(step, Step):
                raise TypeError("Every pipeline step must inherit from Step.")
            configured.append((step_config(step), step))

        PipelineConfig.model_validate(
            {"steps": [config.model_dump() for config, _ in configured]}
        )
        self._steps = tuple(configured)

    @classmethod
    def from_config(
        cls, config: PipelineConfig, *, openai_client: Any | None = None
    ) -> Guardrails:
        if not isinstance(config, PipelineConfig):
            raise TypeError("Guardrails requires a PipelineConfig.")
        configured = tuple(
            (step, cls._make_definition(step, openai_client)) for step in config.steps
        )
        instance = cls.__new__(cls)
        instance._steps = configured
        return instance

    @staticmethod
    def _make_definition(step: PipelineStepConfig, openai_client: Any | None) -> Step:
        if step.kind == "check":
            check_config = CheckConfig(
                name=step.name,
                type=step.type,
                enabled=step.enabled,
                params=step.params,
            )
            operation = create_check(
                check_config,
                openai_client=openai_client,
            )
            return CheckStep(
                name=step.name,
                source=step.input,
                using=operation,
                enabled=step.enabled,
            )

        transform_config = TransformConfig(
            name=step.name,
            type=step.type,
            enabled=step.enabled,
            params=step.params,
        )
        operation = create_transform(transform_config, openai_client=openai_client)
        return TransformStep(
            name=step.name,
            source=step.input,
            target=step.output or "",
            using=operation,
            enabled=step.enabled,
        )

    @classmethod
    def from_dict(
        cls, raw: dict[str, Any], *, openai_client: Any | None = None
    ) -> Guardrails:
        return cls.from_config(parse_config(raw), openai_client=openai_client)

    @classmethod
    def from_yaml(
        cls, path: str | Path, *, openai_client: Any | None = None
    ) -> Guardrails:
        return cls.from_config(load_config(path), openai_client=openai_client)

    @staticmethod
    def _collect(
        result: TransformResult | CheckResult,
        outputs: dict[str, Any],
    ) -> None:
        if isinstance(result, TransformResult):
            outputs[result.output_name] = result.value

    @staticmethod
    def _report(
        outputs: dict[str, Any], step_results: list[TransformResult | CheckResult]
    ) -> GuardrailsReport:
        return GuardrailsReport(
            outputs=outputs,
            step_results=StepResults(items=tuple(step_results)),
        )

    def _run_step(
        self,
        config: PipelineStepConfig,
        step: Step,
        data: Any,
        outputs: dict[str, Any],
    ) -> TransformResult | CheckResult:
        started = time.perf_counter()
        try:
            value = _resolve_reference(config.input, data, outputs)
            return step.run(value)
        except Exception as exc:
            logger.exception(
                "Pipeline step %r raised an unexpected exception", config.name
            )
            elapsed_ms = (time.perf_counter() - started) * 1000
            return step.error_result(exc, elapsed_ms)

    def run(self, data: Any) -> GuardrailsReport:
        outputs: dict[str, Any] = {}
        step_results: list[TransformResult | CheckResult] = []

        for config, step in self._steps:
            if not config.enabled:
                continue
            result = self._run_step(config, step, data, outputs)
            self._collect(result, outputs)
            step_results.append(result)

        return self._report(outputs, step_results)

    async def arun(self, data: Any) -> GuardrailsReport:
        outputs: dict[str, Any] = {}
        step_results: list[TransformResult | CheckResult] = []

        for config, step in self._steps:
            if not config.enabled:
                continue
            started = time.perf_counter()
            try:
                value = _resolve_reference(config.input, data, outputs)
                result = await step.arun(value)
            except Exception as exc:
                logger.exception(
                    "Pipeline step %r raised an unexpected exception", config.name
                )
                elapsed_ms = (time.perf_counter() - started) * 1000
                result = step.error_result(exc, elapsed_ms)
            self._collect(result, outputs)
            step_results.append(result)

        return self._report(outputs, step_results)
