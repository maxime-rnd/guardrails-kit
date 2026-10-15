"""Resolve Pydantic models from import paths or class objects."""

from __future__ import annotations

import importlib

from pydantic import BaseModel

from ..exceptions import ModelLoadError


def load_model(path: str) -> type[BaseModel]:
    """Import and return the Pydantic model class designated by a dotted path."""
    if not isinstance(path, str):
        raise ModelLoadError(f"Model path must be a string, got {type(path).__name__}.")
    module_name, sep, attr = path.rpartition(".")
    if not sep or not module_name or not attr:
        raise ModelLoadError(
            f"Invalid model path {path!r}: expected 'package.module.ClassName'."
        )

    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # a module may raise anything at import time
        raise ModelLoadError(
            f"Cannot import module {module_name!r} for model {path!r}: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    try:
        obj = getattr(module, attr)
    except AttributeError as exc:
        raise ModelLoadError(
            f"Module {module_name!r} has no attribute {attr!r}."
        ) from exc

    if not (isinstance(obj, type) and issubclass(obj, BaseModel)):
        raise ModelLoadError(f"{path!r} is not a subclass of pydantic.BaseModel.")
    return obj


def resolve_model(model: str | type[BaseModel]) -> type[BaseModel]:
    """Return a Pydantic model class from either a class or dotted import path."""
    if isinstance(model, str):
        return load_model(model)
    if isinstance(model, type) and issubclass(model, BaseModel):
        return model
    raise ModelLoadError(
        "Model must be a dotted import path or a pydantic.BaseModel subclass."
    )
