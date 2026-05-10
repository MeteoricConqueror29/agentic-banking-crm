"""Structured payloads for high-value customer intelligence queries."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HighValueCustomerFilters(BaseModel):
    """Thresholds and optional segment filters for ranking customers from DuckDB.

    All minimum filters are combined with AND semantics. When ``loan_intent``
    is set, only customers with that exact intent label are returned (in
    addition to satisfying the numeric thresholds).
    """

    model_config = ConfigDict(str_strip_whitespace=True, frozen=True)

    min_relationship_score: float = Field(
        0.0,
        ge=0.0,
        description="Minimum composite relationship score (0–100 scale in processed data).",
    )
    min_income: float = Field(
        0.0,
        ge=0.0,
        description="Minimum annual income in the processed customers table.",
    )
    min_credit_score: int = Field(
        0,
        ge=0,
        le=900,
        description="Minimum credit score.",
    )
    loan_intent: str | None = Field(
        None,
        description="When provided, restrict to this loan intent value (exact match).",
    )

    @field_validator("loan_intent", mode="before")
    @classmethod
    def empty_loan_intent_to_none(cls, value: object) -> str | None:
        """Treat blank strings as 'no filter' so agents can omit the segment."""
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return str(value).strip()


class HighValueCustomer(BaseModel):
    """One customer row returned by the intelligence query, aligned with ``customers`` CSV."""

    model_config = ConfigDict(extra="ignore")

    customer_id: str
    age: int | None = None
    gender: str | None = None
    education: str | None = None
    income: float
    employment_experience: int | None = None
    home_ownership: str | None = None
    credit_score: int
    loan_intent: str
    loan_status: int
    relationship_score: float


class HighValueCustomerQueryResult(BaseModel):
    """Stable response shape for CRM agents and APIs consuming the intelligence tool."""

    customers: list[HighValueCustomer] = Field(
        default_factory=list,
        description="Customers matching filters, sorted by relationship_score descending.",
    )
    total_matching: int = Field(
        ...,
        ge=0,
        description="Count of rows returned for this query (same as len(customers) unless paginated).",
    )
