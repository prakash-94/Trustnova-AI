"""ML alerts in the AML Center: the sync into the app database, the reason sentences and the /aml routes.

Uses a throwaway SQLite file, never banking.db, and never calls Databricks.
"""
import asyncio
import json
from datetime import date, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text

from src.api import aml_reasons
from src.api.routes import aml
from src.data import sync_ml_alerts as sync


def _row(alert_id="HIS-300-HIS:1:A", account="HIS:1:A", day=300, score=0.97, rank=1, variant="HIS",
         reasons=None, sender=True):
    reasons = reasons if reasons is not None else [
        {"feature": "payment_format_code", "contribution": 5.6, "value": 0.0},
        {"feature": "pt_best_gap", "contribution": 4.4, "value": 0.0},
        {"feature": "first_time_pair", "contribution": 1.6, "value": 1.0},
        {"feature": "pt_chain_len", "contribution": 1.1, "value": 6.0},
        {"feature": "log_amount_usd", "contribution": 1.0, "value": 9.604661617255173},
    ]
    other = "HIS:2:B"
    values = {
        "alert_id": alert_id, "variant": variant, "account_id": account, "day": str(day),
        "alert_date": str(date(2022, 1, 1) + timedelta(days=day)), "score": str(score), "rank_in_day": str(rank), "n_txn": "12",
        "predicted_pattern": "CYCLE", "pattern_probability": "0.58", "reasons": json.dumps(reasons),
        "m1_version": "3", "m3_version": "3", "top_txn_id": "t1", "top_txn_ts": "2022-10-28 10:15:00",
        "top_from_account": account if sender else other, "top_to_account": other if sender else account,
        "top_amount_usd": "14879.33", "top_payment_format": "ACH", "top_currency": "US Dollar",
        "owner_name": "Corporation #1", "bank_name": "Bank #1",
    }
    return tuple(values[c] for c in sync.COLUMNS)  # Databricks returns every value as a string


@pytest.fixture()
def db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'alerts.db'}")
    monkeypatch.setattr(aml, "engine", engine)
    return engine


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- reasons
def test_reason_sentences():
    e = aml_reasons.explain
    assert e({"feature": "payment_format_code", "value": 0.0}) == "Paid by ACH"
    assert e({"feature": "log_amount_usd", "value": 9.604661617255173}) == "Payment amount: $14,833"
    assert e({"feature": "first_time_pair", "value": 1.0}) == "It is the first ever payment between these two accounts"
    assert "chain of 6 payments" in e({"feature": "pt_chain_len", "value": 6.0})
    assert "difference 0.0%" in e({"feature": "pt_best_gap", "value": 0.0})
    assert e({"feature": "s_d0_n_out", "value": 7.0}) == "Sender: payments sent in earlier today: 7"
    assert e({"feature": "so_p7_n_in", "value": 40.0}).startswith("Sender's owner (all accounts): payments received")
    assert e({"feature": "r_p7_usd_in", "value": 1234.4}) == "Receiver: money received in the previous 7 days: $1,234"
    assert e({"feature": "s_minutes_since_in", "value": -1.0}).endswith("never")
    assert e({"feature": "r_entity_type_code", "value": 3.0}) == "Receiver: owner type Corporation"


def test_unknown_reason_falls_back_to_name_and_value():
    assert aml_reasons.explain({"feature": "brand_new_feature", "value": 2.5}) == "brand_new_feature = 2.50"


# ---------------------------------------------------------------- sync
def test_query_never_reads_ground_truth():
    q = sync.query("trustnova_prod").lower()
    assert "restricted" not in q and "is_laundering" not in q and "pattern_type" not in q


def test_query_rejects_a_bad_catalog_name():
    with pytest.raises(ValueError):
        sync.query("x; DROP TABLE y")


def test_upsert_keeps_analyst_work(db):
    assert sync.upsert(db, [_row(), _row("HIS-300-HIS:3:C", "HIS:3:C", rank=2)], now=datetime(2026, 11, 24)) == 2
    with db.begin() as c:
        c.execute(text("UPDATE ml_alerts SET status = 'reviewing', analyst_id = 'amlanalyst' "
                       "WHERE alert_id = 'HIS-300-HIS:1:A'"))
    sync.upsert(db, [_row(score=0.5)], now=datetime(2026, 11, 25))  # the model re-scored it
    with db.connect() as c:
        r = c.execute(text("SELECT score, status, analyst_id, synced_at FROM ml_alerts "
                           "WHERE alert_id = 'HIS-300-HIS:1:A'")).one()
        n = c.execute(text("SELECT COUNT(*) FROM ml_alerts")).scalar()
    assert (r.score, r.status, r.analyst_id, r.synced_at) == (0.5, "reviewing", "amlanalyst", "2026-11-25T00:00:00")
    assert n == 2


# ---------------------------------------------------------------- routes
def test_routes_before_the_first_sync(db):
    res = run(aml.list_aml_cases(None, None, None, None, 50, 0, current_user=None))
    assert res["source_ready"] is False and res["cases"] == []
    with pytest.raises(HTTPException) as e:
        run(aml.get_aml_case("anything", current_user=None))
    assert e.value.status_code == 404


def test_list_orders_filters_and_summarises(db):
    sync.upsert(db, [
        _row("A", "HIS:1:A", day=300, score=0.97, rank=1),
        _row("B", "HIS:1:B", day=300, score=0.75, rank=2, sender=False),
        _row("C", "LIS:1:C", day=299, score=0.30, rank=1, variant="LIS"),
    ])
    res = run(aml.list_aml_cases(None, None, None, None, 50, 0, current_user=None))
    assert [c["id"] for c in res["cases"]] == ["A", "B", "C"]
    s = res["summary"]
    assert (s["total"], s["critical"], s["high"], s["medium"], s["open"]) == (3, 1, 1, 0, 3)

    a, b = res["cases"][0], res["cases"][1]
    assert a["severity"] == "critical" and a["predicted_pattern"] == "cycle"
    assert a["description"] == "Riskiest payment: $14,879 by ACH to HIS:2:B"
    assert b["description"].endswith("from HIS:2:B")
    assert a["reasons"][0]["text"] == "Paid by ACH" and len(a["reasons"]) == 5
    assert a["total_amount_cents"] == 1487933 and a["model_version"] == "M1 v3 · M3 v3"

    high = run(aml.list_aml_cases(None, "high", None, None, 50, 0, current_user=None))
    assert [c["id"] for c in high["cases"]] == ["B"] and high["total"] == 1
    lis = run(aml.list_aml_cases(None, None, None, "LIS", 50, 0, current_user=None))
    assert [c["id"] for c in lis["cases"]] == ["C"]
    page2 = run(aml.list_aml_cases(None, None, None, None, 1, 1, current_user=None))
    assert [c["id"] for c in page2["cases"]] == ["B"] and page2["total"] == 3


def test_bad_filters_are_rejected(db):
    sync.upsert(db, [_row()])
    for kw in ({"status": "bogus"}, {"severity_": "huge"}, {"simulation": "XYZ"}):
        with pytest.raises(HTTPException) as e:
            aml._filters(kw.get("status"), kw.get("severity_"), None, kw.get("simulation"))
        assert e.value.status_code == 400


def test_get_one_case_and_stats(db):
    sync.upsert(db, [_row()])
    assert run(aml.get_aml_case("HIS-300-HIS:1:A", current_user=None))["account_id"] == "HIS:1:A"
    stats = run(aml.get_aml_summary(current_user=None))
    assert stats["total_cases"] == 1 and stats["by_simulation"] == {"HIS": 1} and stats["high_risk"] == 1
