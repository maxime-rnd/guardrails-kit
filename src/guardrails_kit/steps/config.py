"""Conversion from Python step objects to pipeline configuration models."""

from __future__ import annotations

from ..config import PipelineStepConfig
from ..models import Phase
from .base import Step, operation_type
from .check import CheckStep
from .transform import TransformStep


def step_config(step: Step) -> PipelineStepConfig:
    """Convert a step definition into its serializable config shape."""
    is_transform = isinstance(step, TransformStep)
    return PipelineStepConfig(
        name=step.name,
        kind="transform" if is_transform else "check",
        type=operation_type(step.using),
        phase=Phase(step.phase),
        input=step.source,
        output=step.target if is_transform else None,
        enabled=step.enabled,
        params={},
    )
