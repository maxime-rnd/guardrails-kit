"""Exceptions raised by guardrails_kit.

All of them are raised at load time (configuration, model import, check
construction). Check execution never raises: technical problems are reported
as ``error`` results instead.
"""

from __future__ import annotations


class GuardrailsError(Exception):
    """Base class for every exception raised by the library."""


class ConfigError(GuardrailsError):
    """The YAML configuration is missing, malformed or inconsistent."""


class ModelLoadError(ConfigError):
    """A Pydantic model could not be imported from its dotted path."""
