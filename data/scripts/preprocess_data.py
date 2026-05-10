"""Preprocessing pipeline for the AI-powered banking CRM workflow.

Reads the raw loan and transaction datasets, normalizes them into the
schemas consumed by downstream agents, generates synthetic customer
identifiers that link transactions to customers, and writes the cleaned
outputs to ``data/processed/``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Paths & configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

LOAN_CSV = RAW_DIR / "customer_data" / "loan_data.csv"
TRANSACTIONS_CSV = RAW_DIR / "transactions_data" / "transactions_data.csv"

CUSTOMERS_OUT = PROCESSED_DIR / "customers.csv"
TRANSACTIONS_OUT = PROCESSED_DIR / "transactions.csv"

CUSTOMER_LIMIT = 300
TRANSACTION_LIMIT = 3_000
RANDOM_SEED = 42

# Final schemas in the exact column order we want downstream.
CUSTOMER_COLUMNS = [
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
]

TRANSACTION_COLUMNS = [
    "transaction_id",
    "customer_id",
    "date",
    "amount",
    "merchant_city",
    "merchant_state",
    "mcc",
    "transaction_type",
    "errors",
]

# Ordered MCC -> transaction_type rules. Each rule is (low, high, label) and
# the first match wins. Built from the official ISO 18245 ranges, simplified
# to the labels the downstream agents care about.
MCC_TYPE_RULES: list[tuple[int, int, str]] = [
    (3000, 3299, "travel"),         # Airlines
    (3300, 3499, "travel"),         # Car rental
    (3500, 3999, "travel"),         # Lodging / hotels
    (4000, 4799, "travel"),         # Transportation services
    (4800, 4999, "utilities"),      # Telecom, cable, utilities
    (5200, 5299, "shopping"),       # Home supply / hardware
    (5300, 5399, "shopping"),       # Wholesale clubs, discount stores
    (5400, 5499, "food"),           # Grocery / supermarkets
    (5500, 5599, "fuel"),           # Automotive / service stations
    (5600, 5699, "shopping"),       # Apparel
    (5700, 5799, "shopping"),       # Misc retail
    (5800, 5829, "food"),           # Restaurants & eating places
    (5900, 5999, "shopping"),       # Misc retail
    (7000, 7299, "travel"),         # Hotels & personal services
    (7800, 7999, "entertainment"),  # Recreation, theaters, amusement
    (8000, 8099, "utilities"),      # Health services treated as essentials
]

# Specific MCCs that should override the range rule above.
MCC_TYPE_OVERRIDES: dict[int, str] = {
    4829: "utilities",   # Money transfer
    5411: "food",        # Grocery
    5541: "fuel",        # Service stations
    5542: "fuel",        # Automated fuel dispensers
    5812: "food",        # Eating places
    5813: "entertainment",  # Bars / lounges
    5814: "food",        # Fast food
    5912: "utilities",   # Pharmacies
    7011: "travel",      # Lodging
    7832: "entertainment",  # Movie theaters
    7995: "entertainment",  # Gambling
}

DEFAULT_TRANSACTION_TYPE = "purchase"

# Weights for the relationship_score heuristic. Must sum to 1.0.
RELATIONSHIP_WEIGHTS = {
    "credit_score": 0.5,
    "income": 0.3,
    "employment_experience": 0.2,
}

# Reference ranges used to normalize each component to [0, 1].
RELATIONSHIP_NORMALIZATION = {
    "credit_score": (300, 850),     # FICO-like range
    "income": (0, 200_000),         # USD/year cap for normalization
    "employment_experience": (0, 30),  # years cap
}

# Mapping from raw loan_data columns -> normalized customer columns.
LOAN_TO_CUSTOMER_RENAME = {
    "person_age": "age",
    "person_gender": "gender",
    "person_education": "education",
    "person_income": "income",
    "person_emp_exp": "employment_experience",
    "person_home_ownership": "home_ownership",
    "credit_score": "credit_score",
    "loan_intent": "loan_intent",
    "loan_status": "loan_status",
}

# Mapping from raw transactions columns -> normalized transaction columns.
TRANSACTIONS_RENAME = {
    "id": "transaction_id",
    "date": "date",
    "amount": "amount",
    "merchant_city": "merchant_city",
    "merchant_state": "merchant_state",
    "mcc": "mcc",
    "errors": "errors",
}


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def to_snake_case(name: str) -> str:
    """Convert an arbitrary column label to snake_case."""
    name = str(name).strip()
    name = re.sub(r"[\s\-/]+", "_", name)
    name = re.sub(r"(?<!^)(?=[A-Z])", "_", name)
    name = re.sub(r"[^0-9a-zA-Z_]", "", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name.lower()


def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``df`` with snake_case column names."""
    df = df.copy()
    df.columns = [to_snake_case(col) for col in df.columns]
    return df


def load_csv(path: Path, *, nrows: int | None = None, **read_kwargs) -> pd.DataFrame:
    """Load a CSV with sensible defaults and snake_case columns."""
    if not path.exists():
        raise FileNotFoundError(f"Expected dataset at {path}")
    df = pd.read_csv(path, nrows=nrows, low_memory=False, **read_kwargs)
    return clean_column_names(df)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def make_customer_ids(n: int, prefix: str = "CUST", width: int = 5) -> list[str]:
    """Generate stable, zero-padded synthetic customer ids."""
    return [f"{prefix}_{i:0{width}d}" for i in range(1, n + 1)]


def parse_currency(series: pd.Series) -> pd.Series:
    """Strip currency symbols/commas from a string series and cast to float."""
    cleaned = (
        series.astype(str)
        .str.replace(r"[\$,]", "", regex=True)
        .str.strip()
        .replace({"": np.nan, "nan": np.nan, "None": np.nan})
    )
    return pd.to_numeric(cleaned, errors="coerce")


def normalize_to_unit(
    series: pd.Series, low: float, high: float
) -> pd.Series:
    """Linearly scale ``series`` to [0, 1] using ``low``/``high`` bounds."""
    if high <= low:
        raise ValueError(f"Invalid normalization range: ({low}, {high})")
    numeric = pd.to_numeric(series, errors="coerce")
    scaled = (numeric - low) / (high - low)
    return scaled.clip(lower=0.0, upper=1.0).fillna(0.0)


# ---------------------------------------------------------------------------
# Feature engineering helpers
# ---------------------------------------------------------------------------


def classify_mcc(mcc: int | float | None) -> str:
    """Map a single MCC value to one of the known transaction_type labels."""
    if mcc is None or pd.isna(mcc):
        return DEFAULT_TRANSACTION_TYPE
    code = int(mcc)
    if code in MCC_TYPE_OVERRIDES:
        return MCC_TYPE_OVERRIDES[code]
    for low, high, label in MCC_TYPE_RULES:
        if low <= code <= high:
            return label
    return DEFAULT_TRANSACTION_TYPE


def derive_transaction_type(mcc_series: pd.Series) -> pd.Series:
    """Vectorized wrapper around :func:`classify_mcc` for a column of MCCs."""
    return mcc_series.map(classify_mcc).astype("string")


def compute_relationship_score(
    df: pd.DataFrame,
    weights: dict[str, float] = RELATIONSHIP_WEIGHTS,
    ranges: dict[str, tuple[float, float]] = RELATIONSHIP_NORMALIZATION,
) -> pd.Series:
    """Combine credit_score, income, and employment_experience into a 0-100 score.

    Each component is min-max normalized against its reference range, then
    blended with the configured weights and rescaled to a 0-100 integer so
    the value is easy to display in a CRM UI.
    """
    if not np.isclose(sum(weights.values()), 1.0):
        raise ValueError(f"Relationship weights must sum to 1.0, got {weights}")

    components = {
        col: normalize_to_unit(df[col], *ranges[col]) for col in weights
    }
    blended = sum(components[col] * weight for col, weight in weights.items())
    return (blended * 100).round().astype("Int64")


# ---------------------------------------------------------------------------
# Domain-specific builders
# ---------------------------------------------------------------------------


def build_customers(loan_df: pd.DataFrame, limit: int = CUSTOMER_LIMIT) -> pd.DataFrame:
    """Normalize the loan dataset into the customers schema."""
    missing = set(LOAN_TO_CUSTOMER_RENAME) - set(loan_df.columns)
    if missing:
        raise KeyError(f"loan_data.csv is missing expected columns: {sorted(missing)}")

    customers = loan_df.rename(columns=LOAN_TO_CUSTOMER_RENAME).copy()
    customers = customers.drop_duplicates().head(limit).reset_index(drop=True)
    customers.insert(0, "customer_id", make_customer_ids(len(customers)))

    customers["age"] = pd.to_numeric(customers["age"], errors="coerce").astype("Int64")
    customers["income"] = pd.to_numeric(customers["income"], errors="coerce")
    customers["employment_experience"] = pd.to_numeric(
        customers["employment_experience"], errors="coerce"
    ).astype("Int64")
    customers["credit_score"] = pd.to_numeric(
        customers["credit_score"], errors="coerce"
    ).astype("Int64")
    customers["loan_status"] = pd.to_numeric(
        customers["loan_status"], errors="coerce"
    ).astype("Int64")

    for col in ["gender", "education", "home_ownership", "loan_intent"]:
        customers[col] = customers[col].astype("string").str.strip()

    customers["relationship_score"] = compute_relationship_score(customers)

    return customers[CUSTOMER_COLUMNS]


def build_transactions(
    transactions_df: pd.DataFrame,
    customer_ids: Iterable[str],
    limit: int = TRANSACTION_LIMIT,
    seed: int = RANDOM_SEED,
) -> pd.DataFrame:
    """Normalize the transactions dataset and link rows to synthetic customers."""
    missing = set(TRANSACTIONS_RENAME) - set(transactions_df.columns)
    if missing:
        raise KeyError(
            f"transactions_data.csv is missing expected columns: {sorted(missing)}"
        )

    transactions = transactions_df.rename(columns=TRANSACTIONS_RENAME).copy()
    transactions = transactions.head(limit).reset_index(drop=True)

    transactions["customer_id"] = assign_synthetic_customer_ids(
        transactions_df.get("client_id", pd.Series(range(len(transactions)))).head(limit),
        customer_ids,
        seed=seed,
    )

    transactions["date"] = pd.to_datetime(transactions["date"], errors="coerce")
    transactions["amount"] = parse_currency(transactions["amount"])
    transactions["mcc"] = pd.to_numeric(transactions["mcc"], errors="coerce").astype(
        "Int64"
    )
    transactions["errors"] = (
        transactions["errors"].astype("string").str.strip().replace({"": pd.NA})
    )
    for col in ["merchant_city", "merchant_state"]:
        transactions[col] = transactions[col].astype("string").str.strip()

    transactions["transaction_id"] = transactions["transaction_id"].astype("string")
    transactions["transaction_type"] = derive_transaction_type(transactions["mcc"])

    return transactions[TRANSACTION_COLUMNS]


def assign_synthetic_customer_ids(
    raw_client_ids: pd.Series,
    customer_ids: Iterable[str],
    seed: int = RANDOM_SEED,
) -> pd.Series:
    """Map each raw client id to one of the synthetic customer ids.

    Each unique raw client id is consistently mapped to the same synthetic
    customer so that a customer's transactions stay grouped together. The
    mapping is randomized (with a fixed seed) but deterministic.
    """
    customer_pool = list(customer_ids)
    if not customer_pool:
        raise ValueError("customer_ids must not be empty")

    rng = np.random.default_rng(seed)
    unique_ids = pd.Series(raw_client_ids).dropna().unique()
    assigned = rng.choice(customer_pool, size=len(unique_ids), replace=True)
    mapping = dict(zip(unique_ids, assigned))

    fallback = customer_pool[0]
    return raw_client_ids.map(mapping).fillna(fallback).astype("string")


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def summarize(name: str, df: pd.DataFrame, sample_rows: int = 5) -> None:
    """Print a quick QA summary for a dataframe."""
    print(f"\n=== {name} ===")
    print(f"shape: {df.shape}")
    print("sample:")
    print(df.head(sample_rows).to_string(index=False))
    nulls = df.isna().sum()
    print("nulls:")
    print(nulls.to_string())


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------


def run_pipeline() -> tuple[pd.DataFrame, pd.DataFrame]:
    ensure_dir(PROCESSED_DIR)

    print(f"Loading customers from {LOAN_CSV} ...")
    loan_df = load_csv(LOAN_CSV)

    print(
        f"Loading first {TRANSACTION_LIMIT} transactions from {TRANSACTIONS_CSV} ..."
    )
    transactions_raw = load_csv(TRANSACTIONS_CSV, nrows=TRANSACTION_LIMIT)

    customers = build_customers(loan_df, limit=CUSTOMER_LIMIT)
    transactions = build_transactions(
        transactions_raw,
        customer_ids=customers["customer_id"],
        limit=TRANSACTION_LIMIT,
    )

    customers.to_csv(CUSTOMERS_OUT, index=False)
    transactions.to_csv(TRANSACTIONS_OUT, index=False)
    print(f"\nWrote {CUSTOMERS_OUT.relative_to(PROJECT_ROOT)}")
    print(f"Wrote {TRANSACTIONS_OUT.relative_to(PROJECT_ROOT)}")

    summarize("customers", customers)
    summarize("transactions", transactions)

    coverage = transactions["customer_id"].nunique()
    print(
        f"\nLinked transactions to {coverage}/{len(customers)} customers "
        f"({coverage / len(customers):.0%} coverage)."
    )

    return customers, transactions


if __name__ == "__main__":
    run_pipeline()
