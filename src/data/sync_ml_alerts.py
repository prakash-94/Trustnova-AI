"""Copy the ML model's alerts from Databricks into the app database, so the AML Center screen never waits on
Databricks.

    python -m src.data.sync_ml_alerts                       # catalog trustnova_prod, Databricks CLI profile trustnova
    python -m src.data.sync_ml_alerts --catalog trustnova_staging --profile trustnova

It reads `<catalog>.ml.ml_alerts` (written by the `ml_score` job) joined to the alert's riskiest transaction and
the account's owner and bank, and upserts them into the `ml_alerts` table of the app database (`DATABASE_URL`,
SQLite `banking.db` today, Supabase Postgres later). Running it again updates the model's fields but keeps what
analysts did (status, assigned analyst), so it is safe to schedule nightly.

Ground truth (`restricted.*`) is never read: the app must not know which alerts are real laundering.
"""
from __future__ import annotations

import argparse
import os
import re
import time
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.engine import Engine

COLUMNS = ("alert_id", "variant", "account_id", "day", "alert_date", "score", "rank_in_day", "n_txn",
           "predicted_pattern", "pattern_probability", "reasons", "m1_version", "m3_version",
           "top_txn_id", "top_txn_ts", "top_from_account", "top_to_account", "top_amount_usd",
           "top_payment_format", "top_currency", "owner_name", "bank_name")

DDL = """
CREATE TABLE IF NOT EXISTS ml_alerts (
    alert_id            TEXT PRIMARY KEY,
    variant             TEXT NOT NULL,
    account_id          TEXT NOT NULL,
    day                 INTEGER NOT NULL,
    alert_date          TEXT NOT NULL,
    score               REAL NOT NULL,
    rank_in_day         INTEGER,
    n_txn               INTEGER,
    predicted_pattern   TEXT,
    pattern_probability REAL,
    reasons             TEXT,
    m1_version          TEXT,
    m3_version          TEXT,
    top_txn_id          TEXT,
    top_txn_ts          TEXT,
    top_from_account    TEXT,
    top_to_account      TEXT,
    top_amount_usd      REAL,
    top_payment_format  TEXT,
    top_currency        TEXT,
    owner_name          TEXT,
    bank_name           TEXT,
    status              TEXT NOT NULL DEFAULT 'open',
    analyst_id          TEXT,
    synced_at           TEXT NOT NULL
)
"""
INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_ml_alerts_date ON ml_alerts (alert_date, rank_in_day)",
    "CREATE INDEX IF NOT EXISTS ix_ml_alerts_account ON ml_alerts (account_id)",
    "CREATE INDEX IF NOT EXISTS ix_ml_alerts_status ON ml_alerts (status)",
)

_CATALOG = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def query(catalog: str) -> str:
    if not _CATALOG.match(catalog):
        raise ValueError(f"not a catalog name: {catalog!r}")
    return f"""
SELECT a.alert_id, a.variant, a.account_id, a.day,
       CAST(date_add(DATE'2022-01-01', a.day) AS STRING) AS alert_date,
       a.score, a.rank_in_day, a.n_txn, a.predicted_pattern, a.pattern_probability, a.reasons,
       a.m1_version, a.m3_version, a.top_txn_id,
       CAST(t.ts AS STRING) AS top_txn_ts, t.from_account AS top_from_account, t.to_account AS top_to_account,
       t.amount_paid_usd AS top_amount_usd, t.payment_format AS top_payment_format, t.paid_currency AS top_currency,
       acc.entity_name AS owner_name, acc.bank_name
FROM {catalog}.ml.ml_alerts a
LEFT JOIN {catalog}.silver.transactions t ON t.txn_id = a.top_txn_id AND t.variant = a.variant
LEFT JOIN {catalog}.silver.accounts acc ON acc.account_id = a.account_id AND acc.variant = a.variant
"""


def fetch(catalog: str, profile: str | None, warehouse_id: str | None) -> list[tuple]:
    """Run the query on a Databricks SQL warehouse and return every row (all pages)."""
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.sql import Disposition, Format

    w = WorkspaceClient(profile=profile) if profile else WorkspaceClient()
    wid = warehouse_id or next(iter(w.warehouses.list())).id
    r = w.statement_execution.execute_statement(warehouse_id=wid, statement=query(catalog), wait_timeout="50s",
                                                disposition=Disposition.INLINE, format=Format.JSON_ARRAY)
    while r.status.state.value in ("PENDING", "RUNNING"):
        time.sleep(3)
        r = w.statement_execution.get_statement(r.statement_id)
    if r.status.state.value != "SUCCEEDED":
        raise RuntimeError(f"Databricks query failed: {r.status.error}")
    names = [c.name for c in r.manifest.schema.columns]
    if tuple(names) != COLUMNS:
        raise RuntimeError(f"unexpected columns from Databricks: {names}")
    rows, chunk = list(r.result.data_array or []), r.result
    while chunk.next_chunk_index is not None:
        chunk = w.statement_execution.get_statement_result_chunk_n(r.statement_id, chunk.next_chunk_index)
        rows.extend(chunk.data_array or [])
    return [tuple(row) for row in rows]


def _typed(row: Sequence) -> dict:
    d = dict(zip(COLUMNS, row, strict=True))
    for k in ("day", "rank_in_day", "n_txn"):
        d[k] = int(d[k]) if d[k] is not None else None
    for k in ("score", "pattern_probability", "top_amount_usd"):
        d[k] = float(d[k]) if d[k] is not None else None
    return d


def upsert(engine: Engine, rows: Iterable[Sequence], now: datetime | None = None) -> int:
    """Insert new alerts and refresh the model's fields on existing ones. Analyst fields are never overwritten."""
    stamp = (now or datetime.now(UTC)).replace(tzinfo=None).isoformat(timespec="seconds")
    model_cols = [c for c in COLUMNS if c != "alert_id"]
    sql = text(f"""
        INSERT INTO ml_alerts ({", ".join(COLUMNS)}, synced_at)
        VALUES ({", ".join(":" + c for c in COLUMNS)}, :synced_at)
        ON CONFLICT (alert_id) DO UPDATE SET
        {", ".join(f"{c} = excluded.{c}" for c in model_cols)}, synced_at = excluded.synced_at
    """)
    batch = [{**_typed(r), "synced_at": stamp} for r in rows]
    with engine.begin() as conn:
        conn.execute(text(DDL))
        for ix in INDEXES:
            conn.execute(text(ix))
        if batch:
            conn.execute(sql, batch)
    return len(batch)


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sync-ml-alerts", description=__doc__.split("\n\n")[0])
    p.add_argument("--catalog", default=os.getenv("ML_ALERTS_CATALOG", "trustnova_prod"))
    p.add_argument("--profile", default=os.getenv("DATABRICKS_CONFIG_PROFILE", "trustnova"),
                   help="Databricks CLI profile ('' to use DATABRICKS_HOST / DATABRICKS_TOKEN)")
    p.add_argument("--warehouse-id", default=os.getenv("DATABRICKS_WAREHOUSE_ID"))
    a = p.parse_args(argv)

    from src.models.database import engine

    rows = fetch(a.catalog, a.profile or None, a.warehouse_id)
    n = upsert(engine, rows)
    print(f"synced {n:,} alerts from {a.catalog}.ml.ml_alerts into ml_alerts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
