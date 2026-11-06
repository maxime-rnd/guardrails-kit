"""Generic safety assessment schemas for user input and assistant output.

These are example application schemas, not built-in security guarantees.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class InputSafetyReview(BaseModel):
    """Safety signals that commonly matter for untrusted user input.

    Boolean flags mean the issue is present.
    """

    prompt_injection: bool = Field(
        description="The input tries to override or replace trusted instructions."
    )
    jailbreak: bool = Field(
        description="The input tries to bypass safety constraints or access restrictions."
    )
    harmful_request: bool = Field(
        description="The input requests instructions or assistance that could cause harm."
    )
    abusive_or_hateful_content: bool = Field(
        description="The input contains abusive, harassing, or hateful content."
    )
    risk: Literal["low", "medium", "high", "critical"]
    rationale: str = Field(description="Brief explanation based on the input text.")


class OutputSafetyReview(BaseModel):
    """Safety signals that commonly matter in generated assistant output.

    Boolean flags mean the issue is present.
    """

    harmful_content: bool = Field(
        description="The response enables harm or gives dangerous instructions."
    )
    abusive_or_hateful_content: bool = Field(
        description="The response contains abusive, harassing, or hateful content."
    )
    sensitive_data_disclosure: bool = Field(
        description="The response exposes personal, secret, or confidential data unnecessarily."
    )
    internal_instruction_disclosure: bool = Field(
        description="The response reveals hidden system instructions or private prompts."
    )
    unsupported_claim: bool = Field(
        description="The response makes factual claims not supported by the supplied context."
    )
    risk: Literal["low", "medium", "high", "critical"]
    rationale: str = Field(description="Brief explanation based on the response and supplied context.")
