"""Structured payloads for explainable customer recommendations."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CustomerRecommendation(BaseModel):
    """One explainable banking recommendation for a customer."""

    model_config = ConfigDict(frozen=True)

    recommendation_type: str = Field(
        ...,
        description="Human-readable recommendation label (for CRM and agent prompts).",
    )
    recommendation_reason: str = Field(
        ...,
        min_length=1,
        description="Short explanation grounded in customer and transaction signals.",
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Model/rule confidence from 0.0 (low) to 1.0 (high).",
    )


class RecommendationResponse(BaseModel):
    """Stable response shape for per-customer recommendation generation."""

    model_config = ConfigDict(extra="ignore")

    customer_id: str
    recommendations: list[CustomerRecommendation] = Field(default_factory=list)
