"""Parameterized DuckDB access for transaction analytics (no HTTP layer concerns)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from app.services.duckdb_service import DuckDBService

_SAFE_SQL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _assert_safe_table_identifier(table: str) -> str:
    if not _SAFE_SQL_IDENTIFIER.fullmatch(table):
        raise ValueError(f"Invalid SQL table identifier: {table!r}")
    return table


@dataclass(frozen=True, slots=True)
class CustomerTransactionAggregate:
    """Single-row aggregate for one customer from DuckDB."""

    total_transactions: int
    total_spending: float
    average_transaction_amount: float


class TransactionAnalysisRepository:
    """Runs transaction rollups through :class:`DuckDBService`."""

    def __init__(self, db: DuckDBService) -> None:
        self._db = db

    def fetch_customer_aggregate(
        self,
        customer_id: str,
        *,
        table: str | None = None,
    ) -> CustomerTransactionAggregate:
        resolved_table = table or DuckDBService.TRANSACTIONS_TABLE
        safe_table = _assert_safe_table_identifier(resolved_table)
        sql = f"""
            SELECT
                COUNT(*) AS total_transactions,
                COALESCE(SUM(amount), 0) AS total_spending,
                COALESCE(AVG(amount), 0) AS average_transaction_amount
            FROM {safe_table}
            WHERE customer_id = ?
        """.strip()
        df = self._db.fetch_dataframe_params(sql, [customer_id])
        if df.empty:
            return CustomerTransactionAggregate(0, 0.0, 0.0)
        row = df.iloc[0].replace({np.nan: 0})
        return CustomerTransactionAggregate(
            total_transactions=int(row["total_transactions"]),
            total_spending=float(row["total_spending"]),
            average_transaction_amount=float(row["average_transaction_amount"]),
        )

    def fetch_customer_category_breakdown(
        self,
        customer_id: str,
        *,
        table: str | None = None,
    ) -> pd.DataFrame:
        """Columns: ``transaction_type``, ``transaction_count``, ``total_amount``."""
        resolved_table = table or DuckDBService.TRANSACTIONS_TABLE
        safe_table = _assert_safe_table_identifier(resolved_table)
        sql = f"""
            SELECT
                transaction_type,
                COUNT(*) AS transaction_count,
                COALESCE(SUM(amount), 0) AS total_amount
            FROM {safe_table}
            WHERE customer_id = ?
            GROUP BY transaction_type
            ORDER BY total_amount DESC NULLS LAST, transaction_type ASC
        """.strip()
        return self._db.fetch_dataframe_params(sql, [customer_id])
