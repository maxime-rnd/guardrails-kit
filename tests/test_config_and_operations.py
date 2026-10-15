from __future__ import annotations

import pytest
from pydantic import ValidationError

from guardrails_kit import CheckStatus, ConfigError, Guardrails, TransformStatus
from guardrails_kit.config import PipelineConfig, parse_config
from guardrails_kit.operations.checks import ConditionCheck, ConditionParams, RegexCheck
from guardrails_kit.operations.checks.regex_check import RegexParams
from guardrails_kit.operations.transforms import PIIRedactor


def test_regex_check_pass_fail_and_skip() -> None:
    check = RegexCheck(
        "email-format",
        RegexParams(pattern=r"^[^@]+@[^@]+$", on_missing="skip", field="email"),
    )

    assert check.check({"email": "user@example.com"}).status is CheckStatus.PASS
    assert check.check({"email": "invalid"}).status is CheckStatus.FAIL
    assert check.check({}).status is CheckStatus.SKIPPED


def test_condition_check_compares_selected_value() -> None:
    check = ConditionCheck("minimum", ConditionParams(operator="gte", value=18))

    assert check.check(21).status is CheckStatus.PASS
    assert check.check(16).status is CheckStatus.FAIL


def test_pii_redactor_masks_email_and_name() -> None:
    redactor = PIIRedactor()

    result = redactor.transform("My name is Ada Lovelace. Email ada@example.com")

    assert "ada@example.com" not in result
    assert "Ada Lovelace" not in result
    assert "[EMAIL]" in result
    assert "[PERSON_NAME]" in result


def test_pipeline_config_rejects_invalid_references_and_duplicates() -> None:
    with pytest.raises(ValidationError):
        PipelineConfig.model_validate(
            {
                "version": 2,
                "steps": [
                    {
                        "name": "check-first",
                        "kind": "check",
                        "type": "regex",
                        "phase": "input",
                        "input": "outputs.missing",
                    }
                ],
            }
        )

    with pytest.raises(ConfigError):
        parse_config(
            {
                "version": 2,
                "steps": [
                    {
                        "name": "same",
                        "kind": "check",
                        "type": "regex",
                        "phase": "input",
                        "input": "input.message",
                    },
                    {
                        "name": "same",
                        "kind": "check",
                        "type": "regex",
                        "phase": "input",
                        "input": "input.message",
                    },
                ],
            }
        )


def test_from_dict_builds_operations_without_external_services() -> None:
    guardrails = Guardrails.from_dict(
        {
            "version": 2,
            "steps": [
                {
                    "name": "has-text",
                    "kind": "check",
                    "type": "condition",
                    "phase": "input",
                    "input": "input.message",
                    "params": {"operator": "not_equals", "value": ""},
                },
                {
                    "name": "redact",
                    "kind": "transform",
                    "type": "pii_redaction",
                    "phase": "input",
                    "input": "input.message",
                    "output": "safe_message",
                    "params": {"redact": ["email"]},
                },
            ],
        }
    )

    report = guardrails.validate_input({"message": "Contact user@example.com"})

    assert report.checks[0].status is CheckStatus.PASS
    assert report.transforms[0].status is TransformStatus.SUCCESS
    assert "user@example.com" not in report.get_output("safe_message", str)
