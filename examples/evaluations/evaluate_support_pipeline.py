"""Run a small behavior evaluation from the repository root.

Usage: ``python -m examples.evaluations.evaluate_support_pipeline``
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from guardrails_kit import Guardrails  # noqa: E402


CASES: list[dict[str, Any]] = [
    {
        "name": "double charge",
        "message": "I was charged twice for my monthly subscription.",
        "expected_category": "billing",
        "expect_support_match": True,
    },
    {
        "name": "cannot sign in",
        "message": "I cannot sign in after resetting my password.",
        "expected_category": "account",
        "expect_support_match": True,
    },
    {
        "name": "upload crash",
        "message": "The application crashes when I upload a document.",
        "expected_category": "technical",
        "expect_support_match": True,
    },
    {
        "name": "unrelated question",
        "message": "What is the weather like in Tokyo today?",
        "expected_category": "other",
        "expect_support_match": False,
    },
]


def evaluate() -> bool:
    """Run every example and compare actual behavior with expected behavior."""
    # Keep per-case evaluation output readable; each failed step is summarized below.
    logging.disable(logging.ERROR)
    pipeline = Guardrails.from_yaml(
        ROOT / "examples" / "support" / "pipeline.yaml"
    )
    category_matches = 0
    similarity_matches = 0
    case_matches = 0

    print("Evaluating the support pipeline on known examples\n")
    for case in CASES:
        payload = {
            "customer": {
                "name": "Evaluation User",
                "email": "evaluation@example.com",
                "age": 30,
                "message": case["message"],
            }
        }
        report = pipeline.run(payload)
        classification = report.outputs.get("classification")
        actual_category = getattr(classification, "category", None)
        category_ok = actual_category == case["expected_category"]

        similarity_result = report.step_results["message_is_support_related"]
        actual_support_match = similarity_result.status.value == "pass"
        similarity_ok = actual_support_match == case["expect_support_match"]

        category_matches += int(category_ok)
        similarity_matches += int(similarity_ok)
        case_ok = category_ok and similarity_ok and not report.has_errors
        case_matches += int(case_ok)

        category_label = "OK" if category_ok else "MISMATCH"
        similarity_label = "OK" if similarity_ok else "MISMATCH"
        print(f"[{'PASS' if case_ok else 'FAIL'}] {case['name']}")
        print(
            f"  category: expected={case['expected_category']!r}, "
            f"actual={actual_category!r} ({category_label})"
        )
        print(
            f"  support check: expected={'pass' if case['expect_support_match'] else 'fail'}, "
            f"actual={similarity_result.status.value} ({similarity_label})"
        )
        if report.has_errors:
            print("  pipeline error:", "; ".join(item.message for item in report.errors))

    case_count = len(CASES)
    print("\nSummary")
    print(f"  Cases fully matching expectations: {case_matches}/{case_count}")
    print(f"  Category matches:                 {category_matches}/{case_count}")
    print(f"  Similarity verdict matches:       {similarity_matches}/{case_count}")
    print("\nChange the prompt or threshold, rerun, and compare these results.")
    return case_matches == case_count


if __name__ == "__main__":
    sys.exit(0 if evaluate() else 1)
