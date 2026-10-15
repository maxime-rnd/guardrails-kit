from __future__ import annotations

import asyncio

from guardrails_kit import (
    CheckOperation,
    CheckResult,
    CheckStatus,
    CheckStep,
    Guardrails,
    TransformOperation,
    TransformStep,
    TransformStatus,
)


class Uppercase(TransformOperation):
    type_name = "uppercase"

    def transform(self, value: str) -> str:
        return value.upper()


class EqualsExpected(CheckOperation):
    type_name = "equals_expected"

    def __init__(self, expected: str) -> None:
        super().__init__("equals_expected")
        self.expected = expected

    def check(self, value: str) -> CheckResult:
        passed = value == self.expected
        status = CheckStatus.PASS if passed else CheckStatus.FAIL
        message = "Matched." if passed else "Did not match."
        return self._result(status, message)


class BrokenTransform(TransformOperation):
    type_name = "broken"

    def transform(self, value: object) -> object:
        raise RuntimeError("transform failed")


def make_pipeline(expected: str = "HELLO") -> Guardrails:
    return Guardrails(
        [
            TransformStep(
                name="uppercase",
                source="input.message",
                target="normalized",
                using=Uppercase(),
            ),
            CheckStep(
                name="matches",
                source="outputs.normalized",
                using=EqualsExpected(expected),
            ),
        ]
    )


def test_pipeline_runs_transforms_before_checks_and_routes_outputs() -> None:
    report = make_pipeline().validate_input({"message": "hello"})

    assert report.passed
    assert report.get_output("normalized", str) == "HELLO"
    assert report.transforms[0].status is TransformStatus.SUCCESS
    assert report.checks[0].status is CheckStatus.PASS
    assert report.checks[0].phase.value == "input"


def test_pipeline_records_business_failure() -> None:
    report = make_pipeline(expected="OTHER").validate_input({"message": "hello"})

    assert not report.passed
    assert report.has_failures
    assert report.checks[0].status is CheckStatus.FAIL


def test_pipeline_converts_operation_exceptions_to_error_results() -> None:
    pipeline = Guardrails(
        [
            TransformStep(
                name="broken",
                source="input",
                target="result",
                using=BrokenTransform(),
            )
        ]
    )

    report = pipeline.validate_input("value")

    assert report.has_errors
    assert report.transforms[0].status is TransformStatus.ERROR
    assert report.transforms[0].details["exception_type"] == "RuntimeError"


def test_async_pipeline_uses_same_contracts() -> None:
    report = asyncio.run(make_pipeline().avalidate_input({"message": "hello"}))

    assert report.passed
    assert report.get_output("normalized", str) == "HELLO"

