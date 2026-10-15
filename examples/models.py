"""Business models of the demo application.

These live in the *application*, not in guardrails_kit: the YAML files simply
point to them with their import path.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Customer(BaseModel):
    """Payload received by the application (input phase)."""

    name: str = Field(min_length=1)
    email: str
    age: int = Field(ge=18)
    message: str


class StrictCustomer(Customer):
    """Same as Customer, but rejects unknown fields and limits the message size."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(max_length=500)


class SupportReply(BaseModel):
    """Answer produced by the application or agent (output phase)."""

    answer: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class MessageClassification(BaseModel):
    """Structured result extracted from a support message by a transform."""

    category: Literal["billing", "technical", "account", "other"]
    urgency: Literal["low", "normal", "high"]
    summary: str
