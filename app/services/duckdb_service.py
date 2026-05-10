"""DuckDB access layer for the banking CRM workflow.

Provides a small, reusable facade around a persistent DuckDB file with
customers and transactions loaded from the processed CSV exports.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)

__all__ = ["DuckDBService"]


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _escape_sql_string_literal(value: str) -> str:
    return value.replace("'", "''")


class DuckDBService:
    """Connect to ``data/banking_crm.duckdb`` and hydrate core tables from CSV."""

    CUSTOMERS_TABLE = "customers"
    TRANSACTIONS_TABLE = "transactions"

    def __init__(
        self,
        *,
        project_root: Path | None = None,
        db_filename: str = "banking_crm.duckdb",
        processed_subdir: str = "data/processed",
        customers_csv_name: str = "customers.csv",
        transactions_csv_name: str = "transactions.csv",
        auto_initialize: bool = True,
    ) -> None:
        root = project_root or _default_project_root()
        self._project_root = root.resolve()
        self._db_path = (self._project_root / "data" / db_filename).resolve()
        processed = self._project_root / processed_subdir
        self._customers_csv = (processed / customers_csv_name).resolve()
        self._transactions_csv = (processed / transactions_csv_name).resolve()
        self._conn: duckdb.DuckDBPyConnection | None = None

        if auto_initialize:
            self.initialize()

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            raise RuntimeError("DuckDBService is not initialized; call initialize() first.")
        return self._conn

    def initialize(self) -> None:
        """Open the database file and replace core tables from the latest CSV files."""
        self._ensure_csv_sources()
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                logger.exception("Error while closing existing DuckDB connection before re-init")

        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(self._db_path))
        logger.info("Connected to DuckDB at %s", self._db_path)
        print(f"[DuckDBService] Connected to database file: {self._db_path}")

        self._reload_table_from_csv(
            self.CUSTOMERS_TABLE,
            self._customers_csv,
        )
        self._reload_table_from_csv(
            self.TRANSACTIONS_TABLE,
            self._transactions_csv,
        )

        customer_rows = self._table_row_count(self.CUSTOMERS_TABLE)
        transaction_rows = self._table_row_count(self.TRANSACTIONS_TABLE)
        logger.info(
            "Tables ready: %s (%d rows), %s (%d rows)",
            self.CUSTOMERS_TABLE,
            customer_rows,
            self.TRANSACTIONS_TABLE,
            transaction_rows,
        )
        print(
            f"[DuckDBService] Table '{self.CUSTOMERS_TABLE}' loaded: {customer_rows} rows"
        )
        print(
            f"[DuckDBService] Table '{self.TRANSACTIONS_TABLE}' loaded: {transaction_rows} rows"
        )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def execute_query(self, query: str) -> Any:
        """Run ``query`` and return the DuckDB result relation (caller may ``.df()`` / ``.fetchall()``)."""
        return self.connection.execute(query)

    def fetch_dataframe(self, query: str) -> pd.DataFrame:
        """Execute ``query`` and return the result as a pandas DataFrame."""
        return self.connection.execute(query).df()

    def fetch_one(self, query: str) -> Any:
        """Execute ``query`` and return a single row (or ``None`` if no rows)."""
        return self.connection.execute(query).fetchone()

    def _ensure_csv_sources(self) -> None:
        missing: list[Path] = []
        if not self._customers_csv.is_file():
            missing.append(self._customers_csv)
        if not self._transactions_csv.is_file():
            missing.append(self._transactions_csv)
        if missing:
            paths = ", ".join(str(p) for p in missing)
            raise FileNotFoundError(f"Required CSV file(s) not found: {paths}")

    def _reload_table_from_csv(self, table: str, csv_path: Path) -> None:
        path_sql = _escape_sql_string_literal(str(csv_path))
        # CREATE OR REPLACE keeps a single definition and always reflects the latest CSV.
        sql = f"""
        CREATE OR REPLACE TABLE {table} AS
        SELECT * FROM read_csv_auto('{path_sql}', header=true);
        """
        self.connection.execute(sql)
        logger.info("Loaded table %s from %s", table, csv_path)
        print(f"[DuckDBService] Loaded table '{table}' from {csv_path}")

    def _table_row_count(self, table: str) -> int:
        row = self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        if row is None:
            return 0
        return int(row[0])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    service = DuckDBService(auto_initialize=True)

    customer_count = service.fetch_one(f"SELECT COUNT(*) FROM {service.CUSTOMERS_TABLE}")
    transaction_count = service.fetch_one(f"SELECT COUNT(*) FROM {service.TRANSACTIONS_TABLE}")
    print(f"Customer count: {customer_count[0] if customer_count else 0}")
    print(f"Transaction count: {transaction_count[0] if transaction_count else 0}")

    sample = service.fetch_dataframe(
        f"""
        SELECT customer_id, income, credit_score
        FROM {service.CUSTOMERS_TABLE}
        WHERE credit_score >= 700
        ORDER BY income DESC
        LIMIT 5
        """
    )
    print("Sample query (top customers by income among credit_score >= 700):")
    print(sample.to_string(index=False))

    service.close()
