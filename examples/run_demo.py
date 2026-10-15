"""Run the YAML pipeline from the repository root with ``python -m examples.run_demo``."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from guardrails_kit import Guardrails  # noqa: E402


def main() -> None:
    guardrails = Guardrails.from_yaml(ROOT / "examples" / "guardrails.yaml")
    payload = {
        "customer": {
            "name": "Ada Lovelace",
            "email": "ada@example.com",
            "age": 36,
            "message": "My name is Ada Lovelace. I was charged twice for my subscription.",
        }
    }
    report = guardrails.validate_input(payload)

    print(
        f"passed={report.passed} failures={report.has_failures} errors={report.has_errors}"
    )
    print("\nSteps (in execution order):")
    for index, result in enumerate(report.step_results):
        print(
            f"[{index}] [{result.kind}] [{result.status.value}] "
            f"{result.name}: {result.message}"
        )
    if "safe_message" in report.outputs:
        print("\nSanitized message:", report.get_output("safe_message", str))
    if "classification" in report.outputs:
        print("\nClassification:", report.get_output("classification"))


if __name__ == "__main__":
    main()
