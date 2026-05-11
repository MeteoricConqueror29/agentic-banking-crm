"""Transaction analysis tool for agentic banking CRM workflows."""

from __future__ import annotations

import numpy as np

from app.models.transaction_analysis import (
    BehavioralIndicators,
    CategorySpend,
    TransactionAnalysisResult,
)
from app.repositories.transaction_analysis_repository import TransactionAnalysisRepository
from app.services.duckdb_service import DuckDBService

__all__ = ["TransactionAnalysisTool"]

# Simple CRM-style heuristics (tuned for synthetic / limited demo volumes).
_MIN_TRANSACTIONS_FOR_MIX_PROFILE = 4
_HIGH_TOTAL_SPENDING_USD = 3_500.0
_HIGH_AVERAGE_TICKET_USD = 90.0
_TRAVEL_SPEND_SHARE = 0.25
_ENTERTAINMENT_SPEND_SHARE = 0.20
_UTILITIES_SPEND_SHARE = 0.30


def _share(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return max(0.0, min(1.0, float(numerator) / float(denominator)))


def _category_share_map(breakdown: list[CategorySpend]) -> dict[str, float]:
    return {c.transaction_type: c.share_of_spend for c in breakdown}


def _build_behavioral_indicators(
    *,
    total_transactions: int,
    total_spending: float,
    average_transaction_amount: float,
    shares: dict[str, float],
) -> BehavioralIndicators:
    mix_ok = total_transactions >= _MIN_TRANSACTIONS_FOR_MIX_PROFILE
    high_volume = total_spending >= _HIGH_TOTAL_SPENDING_USD or average_transaction_amount >= _HIGH_AVERAGE_TICKET_USD
    return BehavioralIndicators(
        high_spending_activity=high_volume and total_transactions > 0,
        travel_heavy_customer=mix_ok and shares.get("travel", 0.0) >= _TRAVEL_SPEND_SHARE,
        entertainment_heavy_customer=mix_ok and shares.get("entertainment", 0.0) >= _ENTERTAINMENT_SPEND_SHARE,
        utility_focused_customer=mix_ok and shares.get("utilities", 0.0) >= _UTILITIES_SPEND_SHARE,
    )


def _build_spending_summary(
    customer_id: str,
    aggregate: tuple[int, float, float],
    breakdown: list[CategorySpend],
    indicators: BehavioralIndicators,
) -> str:
    total_tx, total_spend, avg_tx = aggregate
    parts: list[str] = []
    parts.append(
        f"Customer {customer_id} recorded {total_tx} transactions for a total of "
        f"${total_spend:,.2f} with an average ticket of ${avg_tx:,.2f}."
    )
    if breakdown:
        top = breakdown[0]
        parts.append(
            f"Largest category by spend is {top.transaction_type} "
            f"({top.share_of_spend * 100:.1f}% of spend, ${top.total_amount:,.2f})."
        )
    else:
        parts.append("No categorized spend is available for this customer in the ledger.")

    hint: list[str] = []
    if indicators.high_spending_activity:
        hint.append("elevated overall spending activity")
    if indicators.travel_heavy_customer:
        hint.append("travel-heavy mix")
    if indicators.entertainment_heavy_customer:
        hint.append("entertainment-heavy mix")
    if indicators.utility_focused_customer:
        hint.append("utility- and essentials-leaning mix")
    if hint:
        parts.append("Behavioral signals: " + ", ".join(hint) + ".")
    return " ".join(parts)


class TransactionAnalysisTool:
    """Compose :class:`DuckDBService` with a repository for typed transaction insights."""

    def __init__(self, db: DuckDBService) -> None:
        self._repository = TransactionAnalysisRepository(db)

    def analyze_customer_transactions(
        self,
        customer_id: str,
        *,
        top_categories: int = 5,
        table: str | None = None,
    ) -> TransactionAnalysisResult:
        """Return structured metrics and simple behavioral flags for one customer."""
        agg = self._repository.fetch_customer_aggregate(customer_id, table=table)
        df = self._repository.fetch_customer_category_breakdown(customer_id, table=table)

        total_spend = agg.total_spending
        if not df.empty:
            df = df.replace({np.nan: None})
            df["transaction_type"] = (
                df["transaction_type"].astype("string").fillna("unknown").str.strip()
            )
            df.loc[df["transaction_type"] == "", "transaction_type"] = "unknown"

        breakdown: list[CategorySpend] = []
        for _, row in df.iterrows():
            raw_amount = float(row["total_amount"])
            amount = max(0.0, raw_amount)
            breakdown.append(
                CategorySpend(
                    transaction_type=str(row["transaction_type"]),
                    transaction_count=int(row["transaction_count"]),
                    total_amount=amount,
                    share_of_spend=_share(amount, total_spend),
                )
            )

        shares = _category_share_map(breakdown)
        indicators = _build_behavioral_indicators(
            total_transactions=agg.total_transactions,
            total_spending=agg.total_spending,
            average_transaction_amount=agg.average_transaction_amount,
            shares=shares,
        )
        top_n = max(0, int(top_categories))
        top_list = breakdown[:top_n] if top_n else []

        summary = _build_spending_summary(
            customer_id,
            (agg.total_transactions, agg.total_spending, agg.average_transaction_amount),
            breakdown,
            indicators,
        )

        return TransactionAnalysisResult(
            customer_id=customer_id,
            total_transactions=agg.total_transactions,
            total_spending=agg.total_spending,
            average_transaction_amount=agg.average_transaction_amount,
            category_breakdown=breakdown,
            top_spending_categories=top_list,
            spending_behavior_summary=summary,
            behavioral_indicators=indicators,
        )
