from __future__ import annotations

import pytest
from pydantic import ValidationError

from guardrails_kit import CheckOperation, CheckStep, TransformOperation, TransformStep
from guardrails_kit.models import CheckResult, CheckStatus


class PrefixTransform(TransformOperation):
    type_name = "prefix"

    def transform(self, value: str) -> str:
        return f"prefix:{value}"


class AlwaysPassCheck(CheckOperation):
    type_name = "always_pass"

    def check(self, data: object) -> CheckResult:
        return self._result(CheckStatus.PASS, "Passed.")


def test_step_models_are_frozen_and_run_typed_operations() -> None:
    transform = TransformStep(
        name="prefix",
        source="input.value",
        target="prefixed",
        using=PrefixTransform(),
    )
    check = CheckStep(
        name="pass",
        source="outputs.prefixed",
        using=AlwaysPassCheck("pass"),
    )

    assert transform.run("value").value == "prefix:value"
    assert check.run("prefix:value").status is CheckStatus.PASS
    with pytest.raises(ValidationError):
        transform.name = "changed"


def test_step_requires_its_operation_base_type() -> None:
    with pytest.raises(ValidationError):
        CheckStep(name="bad", source="input", using=PrefixTransform())
    with pytest.raises(ValidationError):
        TransformStep(name="bad", source="input", target="out", using=AlwaysPassCheck("bad"))

