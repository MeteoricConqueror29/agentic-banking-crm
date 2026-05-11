"""Structured payloads for per-customer transaction analysis."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CategorySpend(BaseModel):
    """Aggregated spend for one ``transaction_type`` bucket."""

    model_config = ConfigDict(frozen=True)

    transaction_type: str = Field(..., description="Normalized category from MCC mapping.")
    transaction_count: int = Field(..., ge=0)
    total_amount: float = Field(..., ge=0.0)
    share_of_spend: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Fraction of the customer's total spending in this category.",
    )


class BehavioralIndicators(BaseModel):
    """Rule-based flags derived from category mix and volume."""

    model_config = ConfigDict(frozen=True)

    high_spending_activity: bool = Field(
        ...,
        description="Elevated total or average ticket size versus simple CRM thresholds.",
    )
    travel_heavy_customer: bool = Field(
        ...,
        description="Travel category represents a large share of spend.",
    )
    entertainment_heavy_customer: bool = Field(
        ...,
        description="Entertainment category represents a large share of spend.",
    )
    utility_focused_customer: bool = Field(
        ...,
        description="Utilities / essentials category represents a large share of spend.",
    )


class TransactionAnalysisResult(BaseModel):
    """Stable response shape for agents and APIs analyzing transaction behavior."""

    model_config = ConfigDict(extra="ignore")

    customer_id: str
    total_transactions: int = Field(..., ge=0)
    total_spending: float = Field(..., ge=0.0)
    average_transaction_amount: float = Field(..., ge=0.0)
    category_breakdown: list[CategorySpend] = Field(
        default_factory=list,
        description="All categories for the customer, ordered by total_amount descending.",
    )
    top_spending_categories: list[CategorySpend] = Field(
        default_factory=list,
        description="Head of category_breakdown (same ordering, capped for quick scanning).",
    )
    spending_behavior_summary: str = Field(
        ...,
        description="Short natural-language synopsis suitable for CRM narratives.",
    )
    behavioral_indicators: BehavioralIndicators
