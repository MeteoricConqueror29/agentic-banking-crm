"""Parameterized DuckDB access for customer intelligence (no HTTP layer concerns)."""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

from app.models.customer_intelligence import (
    HighValueCustomer,
    HighValueCustomerFilters,
    HighValueCustomerQueryResult,
)
from app.services.duckdb_service import DuckDBService

_SAFE_SQL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_CUSTOMER_SELECT_COLUMNS: tuple[str, ...] = (
    "customer_id",
    "age",
    "gender",
    "education",
    "income",
    "employment_experience",
    "home_ownership",
    "credit_score",
    "loan_intent",
    "loan_status",
    "relationship_score",
)


def _assert_safe_table_identifier(table: str) -> str:
    """Reject dynamic table names that are not simple SQL identifiers."""
    if not _SAFE_SQL_IDENTIFIER.fullmatch(table):
        raise ValueError(f"Invalid SQL table identifier: {table!r}")
    return table


def _rows_to_customers(df: pd.DataFrame) -> list[HighValueCustomer]:
    """Map a query result to Pydantic models, normalizing pandas/NA values."""
    if df.empty:
        return []
    cleaned = df.replace({np.nan: None})
    records: list[dict[str, Any]] = cleaned.to_dict(orient="records")
    return [HighValueCustomer.model_validate(row) for row in records]


def build_high_value_customers_sql(
    *,
    table: str,
    filters: HighValueCustomerFilters,
) -> tuple[str, list[Any]]:
    """Build a parameterized SELECT for high-value customers.

    The returned SQL uses DuckDB ``?`` placeholders; bind parameters in the
    same order as returned in the second tuple element.
    """
    safe_table = _assert_safe_table_identifier(table)
    columns_sql = ", ".join(_CUSTOMER_SELECT_COLUMNS)
    base_where = """
        relationship_score >= ?
        AND income >= ?
        AND credit_score >= ?
    """.strip()
    params: list[Any] = [
        filters.min_relationship_score,
        filters.min_income,
        filters.min_credit_score,
    ]
    if filters.loan_intent is not None:
        where_sql = f"{base_where} AND loan_intent = ?"
        params.append(filters.loan_intent)
    else:
        where_sql = base_where

    sql = f"""
        SELECT {columns_sql}
        FROM {safe_table}
        WHERE {where_sql}
        ORDER BY relationship_score DESC, customer_id ASC
    """.strip()
    return sql, params


class CustomerIntelligenceRepository:
    """Runs customer intelligence queries through :class:`DuckDBService`."""

    def __init__(self, db: DuckDBService) -> None:
        self._db = db

    def fetch_high_value_customers(
        self,
        filters: HighValueCustomerFilters,
        *,
        table: str | None = None,
    ) -> HighValueCustomerQueryResult:
        """Return customers at or above the configured thresholds, ranked by relationship score."""
        resolved_table = table or DuckDBService.CUSTOMERS_TABLE
        sql, params = build_high_value_customers_sql(table=resolved_table, filters=filters)
        df = self._db.fetch_dataframe_params(sql, params)
        customers = _rows_to_customers(df)
        return HighValueCustomerQueryResult(
            customers=customers,
            total_matching=len(customers),
        )

    def fetch_customer_by_id(
        self,
        customer_id: str,
        *,
        table: str | None = None,
    ) -> HighValueCustomer | None:
        """Return one customer profile by ``customer_id`` or ``None`` if absent."""
        resolved_table = table or DuckDBService.CUSTOMERS_TABLE
        safe_table = _assert_safe_table_identifier(resolved_table)
        columns_sql = ", ".join(_CUSTOMER_SELECT_COLUMNS)
        sql = f"""
            SELECT {columns_sql}
            FROM {safe_table}
            WHERE customer_id = ?
            LIMIT 1
        """.strip()
        df = self._db.fetch_dataframe_params(sql, [customer_id])
        customers = _rows_to_customers(df)
        if not customers:
            return None
        return customers[0]
