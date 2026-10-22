"""Resolve Pydantic models from import paths or class objects."""

from __future__ import annotations

import importlib
import keyword
import re
from collections.abc import Mapping
from typing import Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, create_model

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


def resolve_model(
    model: str | type[BaseModel] | Mapping[str, Any],
) -> type[BaseModel]:
    """Resolve a Pydantic class, import path, or inline JSON Schema."""
    if isinstance(model, str):
        return load_model(model)
    if isinstance(model, type) and issubclass(model, BaseModel):
        return model
    if isinstance(model, Mapping):
        return model_from_json_schema(model)
    raise ModelLoadError(
        "Model must be a dotted import path, a pydantic.BaseModel subclass, "
        "or an inline JSON Schema object."
    )


def model_from_json_schema(
    schema: Mapping[str, Any], *, name: str | None = None
) -> type[BaseModel]:
    """Build a nested Pydantic model from a JSON Schema object.

    Supports object, array, string, integer, number, boolean and null types,
    enums, required/optional fields, nullable fields and local ``$ref`` values.
    """
    if not isinstance(schema, Mapping):
        raise ModelLoadError("Inline model schema must be a JSON Schema object.")
    root = dict(schema)
    if root.get("type", "object") != "object":
        raise ModelLoadError("The root of an inline model schema must have type 'object'.")
    model_name = _class_name(name or root.get("title") or "StructuredOutput")

    def resolve_ref(ref: str) -> Mapping[str, Any]:
        if not ref.startswith("#/"):
            raise ModelLoadError(f"Only local JSON Schema references are supported: {ref!r}.")
        current: Any = root
        for segment in ref[2:].split("/"):
            segment = segment.replace("~1", "/").replace("~0", "~")
            if not isinstance(current, Mapping) or segment not in current:
                raise ModelLoadError(f"JSON Schema reference {ref!r} could not be resolved.")
            current = current[segment]
        if not isinstance(current, Mapping):
            raise ModelLoadError(f"JSON Schema reference {ref!r} is not a schema object.")
        return current

    def field_name(property_name: str, used: set[str]) -> str:
        candidate = re.sub(r"\W", "_", property_name)
        if not candidate or candidate[0].isdigit():
            candidate = f"field_{candidate}"
        if keyword.iskeyword(candidate):
            candidate = f"field_{candidate}"
        base = candidate
        suffix = 2
        while candidate in used:
            candidate = f"{base}_{suffix}"
            suffix += 1
        used.add(candidate)
        return candidate

    def make_model(
        current: Mapping[str, Any], current_name: str, ref_stack: tuple[str, ...] = ()
    ) -> type[BaseModel]:
        properties = current.get("properties", {})
        if not isinstance(properties, Mapping):
            raise ModelLoadError(f"Schema {current_name!r} properties must be an object.")
        required = current.get("required", [])
        if not isinstance(required, list) or any(not isinstance(item, str) for item in required):
            raise ModelLoadError(f"Schema {current_name!r} required must be a list of names.")
        unknown_required = set(required) - set(properties)
        if unknown_required:
            raise ModelLoadError(
                f"Schema {current_name!r} requires unknown properties: "
                f"{', '.join(sorted(unknown_required))}."
            )

        fields: dict[str, tuple[Any, Any]] = {}
        used_names: set[str] = set()
        for property_name, property_schema in properties.items():
            if not isinstance(property_name, str) or not isinstance(property_schema, Mapping):
                raise ModelLoadError(f"Schema {current_name!r} has an invalid property.")
            python_name = field_name(property_name, used_names)
            property_type = schema_type(
                property_schema,
                f"{current_name}_{python_name.title().replace('_', '')}",
                ref_stack,
            )
            field_kwargs: dict[str, Any] = {"alias": property_name}
            description = property_schema.get("description")
            if isinstance(description, str):
                field_kwargs["description"] = description

            if property_name in required:
                default: Any = ...
            else:
                property_type = Union[property_type, type(None)]
                default = property_schema.get("default")
            fields[python_name] = (property_type, Field(default, **field_kwargs))

        extra_policy = "allow" if current.get("additionalProperties") is True else "forbid"
        return create_model(
            current_name,
            __config__=ConfigDict(extra=extra_policy, populate_by_name=True),
            **fields,
        )

    def schema_type(
        current: Mapping[str, Any], current_name: str, ref_stack: tuple[str, ...]
    ) -> Any:
        ref = current.get("$ref")
        if isinstance(ref, str):
            if ref in ref_stack:
                raise ModelLoadError(f"Recursive JSON Schema references are not supported: {ref!r}.")
            return schema_type(resolve_ref(ref), current_name, (*ref_stack, ref))

        branches = current.get("anyOf") or current.get("oneOf")
        if branches is not None:
            if not isinstance(branches, list):
                raise ModelLoadError(f"Schema {current_name!r} alternatives must be a list.")
            non_null = [branch for branch in branches if branch.get("type") != "null"]
            if len(non_null) == 1 and len(non_null) != len(branches):
                return Union[schema_type(non_null[0], current_name, ref_stack), type(None)]
            raise ModelLoadError(
                f"Schema {current_name!r}: only nullable anyOf/oneOf is supported."
            )

        enum_values = current.get("enum")
        if enum_values is not None:
            if not isinstance(enum_values, list) or not enum_values:
                raise ModelLoadError(f"Schema {current_name!r} enum must be a non-empty list.")
            if any(isinstance(item, (dict, list)) for item in enum_values):
                raise ModelLoadError(f"Schema {current_name!r} enum values must be scalars.")
            return Literal[tuple(enum_values)]
        if "const" in current:
            return Literal[current["const"]]

        type_value = current.get("type")
        nullable = bool(current.get("nullable"))
        if isinstance(type_value, list):
            nullable = nullable or "null" in type_value
            type_options = [item for item in type_value if item != "null"]
            if len(type_options) != 1:
                raise ModelLoadError(f"Schema {current_name!r} has an unsupported type union.")
            type_value = type_options[0]
        if type_value is None and "properties" in current:
            type_value = "object"

        if type_value == "object":
            result: Any = make_model(current, current_name, ref_stack)
        elif type_value == "array":
            item_schema = current.get("items", {})
            if not isinstance(item_schema, Mapping):
                raise ModelLoadError(f"Schema {current_name!r} array items must be a schema object.")
            result = list[schema_type(item_schema, f"{current_name}Item", ref_stack)]
        elif type_value == "string":
            result = str
        elif type_value == "integer":
            result = int
        elif type_value == "number":
            result = float
        elif type_value == "boolean":
            result = bool
        elif type_value == "null":
            result = type(None)
        else:
            raise ModelLoadError(
                f"Schema {current_name!r} has unsupported or missing type {type_value!r}."
            )
        return Union[result, type(None)] if nullable and type_value != "null" else result

    try:
        return make_model(root, model_name)
    except ModelLoadError:
        raise
    except Exception as exc:
        raise ModelLoadError(
            f"Could not build a Pydantic model from JSON Schema: {type(exc).__name__}: {exc}"
        ) from exc


def _class_name(value: Any) -> str:
    candidate = re.sub(r"\W", "", str(value))
    if not candidate or candidate[0].isdigit():
        candidate = f"Structured{candidate}"
    return candidate
