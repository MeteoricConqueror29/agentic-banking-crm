"""Structured payloads for the agentic orchestrator (planner) workflow.

These models are the contract between the planner layer and any HTTP / agent
consumer. The planner is the only layer allowed to assemble them; tools stay
focused on their single responsibility.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from app.models.customer_intelligence import HighValueCustomer
from app.models.outreach import OutreachMessageResponse
from app.models.recommendation import CustomerRecommendation
from app.models.transaction_analysis import TransactionAnalysisResult

__all__ = [
    "InterpretedIntent",
    "OrchestrationStep",
    "CustomerOrchestrationResult",
    "OrchestrationSummary",
    "PlannerResponse",
]


class InterpretedIntent(BaseModel):
    """Lightweight, explainable intent produced by the planner's keyword router."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(
        ...,
        description="Canonical intent label, e.g. 'investment_products' or 'travel_rewards_card'.",
    )
    description: str = Field(
        ...,
        description="Human-readable explanation of what the planner inferred from the RM query.",
    )
    matched_keywords: list[str] = Field(
        default_factory=list,
        description="Keywords from the RM query that triggered this intent (empty for default plan).",
    )
    focus_recommendation_type: str | None = Field(
        None,
        description="Recommendation label the planner prioritizes for this intent, if any.",
    )
    required_behavioral_indicator: str | None = Field(
        None,
        description="Behavioral indicator from the transaction tool that a customer must satisfy, if any.",
    )


class OrchestrationStep(BaseModel):
    """One executed phase in the planner's pipeline (for traceability)."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., description="Stable step identifier, e.g. 'retrieve_customers'.")
    status: str = Field(
        "completed",
        description="Lifecycle status: 'completed', 'skipped', or 'failed'.",
    )
    detail: str | None = Field(
        None,
        description="Short, human-readable note about what the step did.",
    )


class CustomerOrchestrationResult(BaseModel):
    """Per-customer bundle: profile, transaction insights, recommendations, and outreach."""

    model_config = ConfigDict(extra="ignore")

    customer: HighValueCustomer
    transaction_analysis: TransactionAnalysisResult
    recommendations: list[CustomerRecommendation] = Field(
        default_factory=list,
        description="Recommendations from the recommendation tool, optionally filtered by intent focus.",
    )
    outreach: OutreachMessageResponse | None = Field(
        None,
        description="Personalized outreach message (omitted if generation was skipped).",
    )


class OrchestrationSummary(BaseModel):
    """Top-level orchestration metadata for observability and downstream agents."""

    model_config = ConfigDict(extra="ignore")

    query: str = Field(..., description="Original (trimmed) RM query string.")
    interpreted_intent: InterpretedIntent
    candidates_retrieved: int = Field(
        ...,
        ge=0,
        description="Customers returned by the customer intelligence tool before per-customer filtering.",
    )
    customers_processed: int = Field(
        ...,
        ge=0,
        description="Customers that survived behavioral and recommendation-focus filters.",
    )
    recommendations_generated: int = Field(..., ge=0)
    outreach_messages_generated: int = Field(..., ge=0)
    steps: list[OrchestrationStep] = Field(
        default_factory=list,
        description="Ordered trace of orchestration phases executed by the planner.",
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp the planner finished assembling this response.",
    )


class PlannerResponse(BaseModel):
    """Unified structured response returned by the planner for an RM query."""

    model_config = ConfigDict(extra="ignore")

    query: str
    interpreted_intent: InterpretedIntent
    matched_customers: list[CustomerOrchestrationResult] = Field(
        default_factory=list,
        description="Customers selected by the planner with all per-customer artifacts attached.",
    )
    orchestration_summary: OrchestrationSummary
