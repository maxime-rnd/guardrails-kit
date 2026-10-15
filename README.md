# Guardrails Kit

Guardrails Kit is a small Python library for building ordered data pipelines. A pipeline can **transform** input (for example, redact text or extract a typed object) and **check** values (for example, validate a schema or compare text with examples).

The package does not require a particular application schema. Pass a dictionary, Pydantic model, dataclass, string, or another value your operations understand.

## Install

From a checkout of this repository:

```bash
python -m pip install -e .
```

To install the development dependency used by the test suite:

```bash
python -m pip install -e ".[dev]"
```

Python 3.11 or newer is required.

## Quick start: Python API, no model required

This example redacts common personal information from text and returns the result under a named output:

```python
from guardrails_kit import Guardrails, TransformStep, PIIRedactor

guardrails = Guardrails([
    TransformStep(
        name="redact_message",
        source="input.message",
        target="safe_message",
        using=PIIRedactor(),
    ),
])

report = guardrails.validate_input({
    "message": "Email Ada at ada@example.com",
})

print(report.get_output("safe_message"))
# Email Ada at [EMAIL]
```

Transforms produce named values that later steps can use. Checks evaluate a value without replacing it. Both kinds of step run in the order supplied to `Guardrails`.

## Configure an OpenAI-compatible model

Copy [`.env.example`](.env.example) to `.env` and adjust the settings. The library loads the nearest `.env` file by searching upward from the current working directory when it creates an OpenAI client. Variables already set in the process environment take precedence.

The example file is set up for a local Ollama server. Ensure Ollama is running and the configured chat and embedding models are available. For the OpenAI API, comment out `OPENAI_BASE_URL` and set `OPENAI_API_KEY` to your key.

```dotenv
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama
OPENAI_MODEL=qwen2.5:0.5b
OPENAI_EMBEDDING_MODEL=nomic-embed-text
```

`OPENAI_MODEL` is the default for `llm_extractor`. `OPENAI_EMBEDDING_MODEL` is the default for `embedding_similarity`. Both can be overridden in their step's `params`. Use models supported by the API endpoint you configured. Do not commit `.env`; it is ignored by Git.

## Use a YAML pipeline

Load the complete example with:

```python
from guardrails_kit import Guardrails

guardrails = Guardrails.from_yaml("examples/guardrails.yaml")
report = guardrails.validate_input({
    "customer": {
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "age": 36,
        "message": "I was charged twice for my subscription.",
    }
})

print(report.get_output("safe_message", str))
print(report.get_output("classification"))
for result in report.step_results:
    print(result.status.value, result.name, result.message)
print(report.step_results[0])
print(report.step_results["customer_matches_schema"])
```

The YAML file uses `version: 2` and an ordered `steps` list. Each step has a `kind` (`transform` or `check`), a registered `type`, a `phase`, an `input` reference, and optional `params`. A transform also declares an `output` name.

- `input.message` reads from the original value passed to `validate_input` or `validate_output`.
- `outputs.safe_message` reads a named transform result produced earlier in the same phase.
- `input` by itself refers to the complete original value.

See [`examples/guardrails.yaml`](examples/guardrails.yaml) for a complete pipeline with PII redaction, structured LLM extraction, schema validation, similarity, and condition checks. LLM and embedding operations need an OpenAI-compatible client; regex and condition operations do not.

## Built-in operations

| Kind | YAML type | Purpose |
| --- | --- | --- |
| Transform | `pii_redaction` | Masks configured email, token, bearer-token, and name patterns. |
| Transform | `llm_extractor` | Uses chat completions to parse text into a Pydantic model. |
| Check | `condition` | Compares a value using operators such as `equals`, `not_equals`, `in`, and `gt`. |
| Check | `embedding_similarity` | Compares text with examples and passes when the closest cosine similarity meets `threshold`. |
| Check | `pydantic` | Validates the input against a Pydantic model. |
| Check | `regex` | Checks whether a pattern is present or forbidden. |

See the `params` for each operation in the example YAML and the corresponding classes under [`src/guardrails_kit/operations`](src/guardrails_kit/operations/).

## Read the report

`validate_input()` and `validate_output()` return a `GuardrailsReport` for that phase. `report.step_results` contains every executed step result in pipeline order. Retrieve an item by index (`report.step_results[0]`) or by its configured step name (`report.step_results["customer_matches_schema"]`), or iterate over the collection. Each result has a `kind` field with the value `"transform"` or `"check"`, so callers can distinguish the result type without inspecting its class. A missing name raises `KeyError`. `report.outputs` maps output names to their original typed Python values; `report.get_output(name, Type)` optionally checks an output's type. For kind-specific access, `report.transforms` and `report.checks` are derived filtered views. Use `report.to_dict()` when you need a serializable representation; its `step_results` array keeps execution order and includes `kind`.

Check statuses have distinct meanings:

- `pass`: the check accepted the value.
- `fail`: the value did not satisfy the check.
- `error`: the check or transform could not run because of a technical problem.
- `skipped`: the check did not apply, for example because a configured missing-field policy asked to skip it.

`report.passed` is false when the report has a failure or an execution error. A failed check is a business/data verdict; an error points to a problem running the operation.

## Add a custom operation in Python

Inherit from `TransformOperation` and implement `transform`, or inherit from `CheckOperation` and implement `check`. A check returns a `CheckResult`; a transform returns the value it produces. Put names, input/output references, phase, and enabled state on the corresponding `TransformStep` or `CheckStep`.

```python
from guardrails_kit import (
    CheckOperation, CheckResult, CheckStatus,
    CheckStep, Guardrails,
)


class NonEmpty(CheckOperation):
    type_name = "non_empty"

    def __init__(self):
        super().__init__("non_empty")

    def check(self, value: str) -> CheckResult:
        if value.strip():
            return self._result(CheckStatus.PASS, "Value is not empty.")
        return self._result(CheckStatus.FAIL, "Value is empty.")


guardrails = Guardrails([
    CheckStep(name="message_present", source="input.message", using=NonEmpty()),
])
report = guardrails.validate_input({"message": "Hello"})
```

The built-in `LLMExtractor` and `EmbeddingSimilarityCheck` can also receive an injected OpenAI-compatible client when constructed in Python, which is useful for tests and custom client settings.

## Repository map

- `src/guardrails_kit/operations/` — reusable check and transform implementations.
- `src/guardrails_kit/steps/` — pipeline step contracts and execution adapters.
- `src/guardrails_kit/config.py` — YAML/dictionary configuration validation.
- `src/guardrails_kit/pipeline.py` — sequential pipeline execution and reports.
- `examples/` — runnable YAML and Python examples, including example Pydantic models.
- `notebooks/` — interactive walkthrough.
- `tests/` — automated unit tests.
- `.github/workflows/ci.yml` — test and compile checks for supported Python versions.

## Try the examples

Run the example pipeline from the repository root:

```bash
python -m examples.run_demo
```

Open [`notebooks/guardrails_kit_demo.ipynb`](notebooks/guardrails_kit_demo.ipynb) for an interactive walkthrough. Run the unit tests with:

```bash
python -m pytest
```

## Current limitation

PII redaction currently uses regex patterns. It is useful as a simple local transform, but name detection is heuristic and it can miss formats or redact false positives. The name detector has a TODO for replacement with a model-based approach.

## End-to-end Python example

This example combines two transforms and two checks. It needs no model or YAML file, and shows how the ordered results correspond to the configured steps:

```python
from guardrails_kit import (
    CheckOperation,
    CheckResult,
    CheckStatus,
    CheckStep,
    Guardrails,
    PIIRedactor,
    TransformOperation,
    TransformStep,
)


class NormalizeWhitespace(TransformOperation):
    type_name = "normalize_whitespace"

    def transform(self, text: str) -> str:
        return " ".join(text.split())


class MessagePresent(CheckOperation):
    type_name = "message_present"

    def __init__(self):
        super().__init__("message_present")

    def check(self, text: str) -> CheckResult:
        if text.strip():
            return self._result(CheckStatus.PASS, "Message is present.")
        return self._result(CheckStatus.FAIL, "Message is empty.")


class WithinCharacterLimit(CheckOperation):
    type_name = "within_character_limit"

    def __init__(self, limit: int):
        super().__init__("within_character_limit")
        self.limit = limit

    def check(self, text: str) -> CheckResult:
        if len(text) <= self.limit:
            return self._result(
                CheckStatus.PASS,
                f"Message has {len(text)} characters (limit: {self.limit}).",
            )
        return self._result(
            CheckStatus.FAIL,
            f"Message has {len(text)} characters; limit is {self.limit}.",
        )


guardrails = Guardrails([
    TransformStep(
        name="redact_personal_data",
        source="input.message",
        target="safe_message",
        using=PIIRedactor(redact=["email", "person_name"]),
    ),
    TransformStep(
        name="normalize_message",
        source="outputs.safe_message",
        target="clean_message",
        using=NormalizeWhitespace(),
    ),
    CheckStep(
        name="message_present",
        source="outputs.clean_message",
        using=MessagePresent(),
    ),
    CheckStep(
        name="message_within_limit",
        source="outputs.clean_message",
        using=WithinCharacterLimit(limit=180),
    ),
])

report = guardrails.validate_input({
    "message": "My name is Ada Lovelace. Email me at ada@example.com.   "
               "I was charged twice for my subscription."
})

for index, result in enumerate(report.step_results):
    print(index, result.kind, result.name, result.status.value, result.message)

clean_message = report.get_output("clean_message", str)
length_check = report.step_results["message_within_limit"]
print("Clean message:", clean_message)
print("Length check passed:", length_check.status is CheckStatus.PASS)
print("Whole pipeline passed:", report.passed)
```
