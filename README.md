# Guardrails Kit

Une petite bibliothèque Python pour transformer et vérifier des données dans un ordre explicite. Un transform produit une sortie nommée, qu’il s’agisse de texte nettoyé ou d’une structure extraite. Un check retourne `pass`, `fail`, `error` ou `skipped`.

## Installation et configuration

```bash
pip install -e .
```

Le client OpenAI lit automatiquement `.env` à la création d'une configuration qui utilise un modèle. Pour Ollama compatible OpenAI :

```dotenv
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama
OPENAI_MODEL=qwen2.5:0.5b
```

## Utiliser une configuration YAML

La configuration d'exemple est [`examples/guardrails.yaml`](examples/guardrails.yaml). Les étapes s'exécutent dans l'ordre. `input.*` lit la requête d'origine et `outputs.*` lit une sortie produite par une étape précédente.

```python
from guardrails_kit import Guardrails

guardrails = Guardrails.from_yaml("examples/guardrails.yaml")
report = guardrails.validate_input(
    {
        "customer": {
            "name": "Ada Lovelace",
            "email": "ada@example.com",
            "age": 36,
            "message": "I was charged twice for my subscription.",
        }
    }
)

print(report.passed, report.has_failures, report.has_errors)
print(report.get_output("safe_message", str))
print(report.get_output("classification"))  # instance Pydantic typée
for check in report.checks:
    print(check.status.value, check.name, check.message)
```

Le rapport sépare les étapes qui produisent des données (`transforms`, `outputs`) des vérifications (`checks`). `report.to_dict()` fournit une représentation sérialisable.

## Définir les étapes directement en Python

En Python, chaque étape déclare son opération (`TransformStep` ou `CheckStep`). Les composants passés à `using` ne portent ni nom ni phase ; ces informations appartiennent à l'étape. Une opération de transformation renvoie directement sa valeur ; `TransformStep` la place dans un `TransformResult`. Une opération de vérification renvoie un `CheckResult`.

Pour créer un transform réutilisable, hérite de `TransformOperation` et implémente `transform`. Son implémentation par défaut de `atransform` exécute cette méthode synchrone hors de la boucle asyncio ; les transforms avec I/O asynchrone peuvent redéfinir `atransform`.

```python
from guardrails_kit import TransformOperation


class NormalizeWhitespace(TransformOperation):
    type_name = "normalize_whitespace"

    def transform(self, value: str) -> str:
        return " ".join(value.split())
```

Puis passe cette instance dans `using=NormalizeWhitespace()` sur une étape `TransformStep`.

```python
from guardrails_kit import (
    CheckOperation,
    CheckResult,
    CheckStatus,
    CheckStep,
    Guardrails,
    LLMExtractor,
    PIIRedactor,
    TransformStep,
)
from examples.models import MessageClassification


class SummaryPresentCheck(CheckOperation):
    type_name = "summary_present"

    def __init__(self):
        super().__init__("summary_present")

    def check(self, summary: str) -> CheckResult:
        present = bool(summary.strip())
        return self._result(
            CheckStatus.PASS if present else CheckStatus.FAIL,
            "Summary is present." if present else "Summary is empty.",
        )


guardrails = Guardrails(
    [
        TransformStep(
            name="redact_message",
            source="input.message",
            target="safe_message",
            using=PIIRedactor(),
        ),
        TransformStep(
            name="classify_message",
            source="outputs.safe_message",
            target="classification",
            using=LLMExtractor(
                output_model=MessageClassification,
                prompt="Classify this support message.",
            ),
        ),
        CheckStep(
            name="summary_present",
            source="outputs.classification.summary",
            using=SummaryPresentCheck(),
        ),
    ]
)

report = guardrails.validate_input({"message": "Please help with my account."})
```

## Étapes disponibles

- `transform / pii_redaction` : masque les informations personnelles reconnues par les regex intégrées.
- `transform / llm_extractor` : extrait une structure Pydantic avec un appel au modèle configuré.
- `check / pydantic` : valide une valeur avec un modèle Pydantic.
- `check / regex` : vérifie un motif, avec possibilité d'interdire les correspondances.
- `check / embedding_similarity` : compare un texte à des exemples avec un seuil configurable.
- `check / condition` : compare une valeur à une constante (`equals`, `not_equals`, `in`, `gt`, etc.).

La détection PII actuelle est une première version basée sur des regex ; elle peut manquer des formats ou produire des faux positifs. Le rapport de transformation ne réexpose pas les valeurs remplacées.

## Démo et notebook

- Lancez `python -m examples.run_demo` depuis la racine du projet.
- Ouvrez [`notebooks/guardrails_kit_demo.ipynb`](notebooks/guardrails_kit_demo.ipynb) pour essayer le pipeline YAML et les règles PII.
