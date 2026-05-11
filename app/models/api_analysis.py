"""API-facing request/response contracts for planner-backed analysis."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.models.customer_intelligence import HighValueCustomer
from app.models.outreach import OutreachMessageResponse
from app.models.planner import InterpretedIntent, OrchestrationSummary, PlannerResponse
from app.models.recommendation import CustomerRecommendation
from app.models.transaction_analysis import TransactionAnalysisResult


class AnalyzeRequest(BaseModel):
    """Input payload for the consolidated planner analysis endpoint."""

    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(..., min_length=1, description="Free-form RM request.")


class CustomerRecommendations(BaseModel):
    """Recommendation list grouped by customer for API consumers."""

    customer_id: str
    recommendations: list[CustomerRecommendation] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    """Clean, API-oriented projection of planner orchestration output."""

    interpreted_intent: InterpretedIntent
    shortlisted_customers: list[HighValueCustomer] = Field(default_factory=list)
    transaction_insights: list[TransactionAnalysisResult] = Field(default_factory=list)
    recommendations: list[CustomerRecommendations] = Field(default_factory=list)
    outreach_messages: list[OutreachMessageResponse] = Field(default_factory=list)
    orchestration_summary: OrchestrationSummary

    @classmethod
    def from_planner_response(cls, planner_response: PlannerResponse) -> "AnalyzeResponse":
        """Transform planner output into a stable API response shape."""
        matched = planner_response.matched_customers
        return cls(
            interpreted_intent=planner_response.interpreted_intent,
            shortlisted_customers=[item.customer for item in matched],
            transaction_insights=[item.transaction_analysis for item in matched],
            recommendations=[
                CustomerRecommendations(
                    customer_id=item.customer.customer_id,
                    recommendations=item.recommendations,
                )
                for item in matched
            ],
            outreach_messages=[item.outreach for item in matched if item.outreach is not None],
            orchestration_summary=planner_response.orchestration_summary,
        )
