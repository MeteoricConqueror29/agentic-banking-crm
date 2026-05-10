"""Customer intelligence tool for agentic banking CRM workflows."""

from __future__ import annotations

from app.models.customer_intelligence import (
    HighValueCustomer,
    HighValueCustomerFilters,
    HighValueCustomerQueryResult,
)
from app.repositories.customer_intelligence_repository import CustomerIntelligenceRepository
from app.services.duckdb_service import DuckDBService

__all__ = [
    "CustomerIntelligenceTool",
    "HighValueCustomer",
    "HighValueCustomerFilters",
    "HighValueCustomerQueryResult",
]


class CustomerIntelligenceTool:
    """Surface high-value customers from the processed ``customers`` DuckDB table.

    This tool composes :class:`DuckDBService` with a dedicated repository so
    SQL stays out of HTTP routes and agent planners can call a single,
    well-typed entry point.

    Typical workflow inputs emphasize ``relationship_score``, ``income``,
    ``credit_score``, and optional ``loan_intent`` segmentation, matching how
    the preprocessing pipeline engineers ``relationship_score`` from credit
    and income signals.
    """

    def __init__(self, db: DuckDBService) -> None:
        self._db = db
        self._repository = CustomerIntelligenceRepository(db)

    def find_high_value_customers(
        self,
        filters: HighValueCustomerFilters | None = None,
        *,
        table: str | None = None,
    ) -> HighValueCustomerQueryResult:
        """Query processed customers with configurable thresholds.

        Args:
            filters: Minimum relationship score, income, and credit score, plus
                optional ``loan_intent``. Defaults include all customers (all
                minimums at zero, no intent filter).
            table: Override DuckDB table name (defaults to
                :attr:`DuckDBService.CUSTOMERS_TABLE`).

        Returns:
            Structured rows sorted by ``relationship_score`` descending, then
            ``customer_id`` for deterministic ordering.
        """
        resolved = filters or HighValueCustomerFilters()
        return self._repository.fetch_high_value_customers(resolved, table=table)
