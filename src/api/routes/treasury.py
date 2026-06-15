import os
from fastapi import APIRouter, Depends
from sqlalchemy import create_engine, text
from src.api.auth import CurrentUser, require_permission

router = APIRouter()
_engine = create_engine(
    os.getenv("DATABASE_URL", "sqlite:///./banking.db"),
    connect_args={"check_same_thread": False},
)


def _ensure():
    with _engine.connect() as c:
        c.execute(text("""CREATE TABLE IF NOT EXISTS treasury_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, instrument TEXT, cusip TEXT,
            position_type TEXT, face_value REAL DEFAULT 0, market_value REAL DEFAULT 0,
            yield_rate REAL DEFAULT 0, duration REAL DEFAULT 0, maturity_date TEXT,
            coupon_rate REAL DEFAULT 0, currency TEXT DEFAULT 'USD', status TEXT DEFAULT 'active',
            updated_at TEXT)"""))
        c.execute(text("""CREATE TABLE IF NOT EXISTS liquidity_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT, metric_name TEXT UNIQUE,
            value REAL DEFAULT 0, threshold REAL DEFAULT 0, status TEXT, updated_at TEXT)"""))
        c.commit()


_ensure()


def _get_dashboard_data() -> dict:
    """Compute treasury dashboard metrics from live account data."""
    with _engine.connect() as conn:
        total_balance_cents = conn.execute(
            text("SELECT COALESCE(SUM(balance_cents), 0) FROM accounts")
        ).fetchone()[0] or 0

        savings_cents = conn.execute(
            text("SELECT COALESCE(SUM(balance_cents), 0) FROM accounts WHERE account_type IN ('savings','checking','premium')")
        ).fetchone()[0] or 0

        customer_count = conn.execute(
            text("SELECT COUNT(*) FROM customers")
        ).fetchone()[0] or 1

    # Derive realistic treasury metrics from deposit base
    total = int(total_balance_cents)
    cash_position = int(total * 0.18)       # ~18% liquid
    hqla = int(total * 0.22)               # High-Quality Liquid Assets
    outflows_30d = int(total * 0.12)       # estimated 30-day net outflows
    securities = int(total * 0.35)         # securities portfolio
    required_reserve = int(total * 0.10)   # 10% reserve requirement
    actual_reserve = int(total * 0.13)     # 13% actual reserve

    lcr = round(hqla / outflows_30d, 2) if outflows_30d else 1.15
    nsfr = round((int(total * 0.55)) / (int(total * 0.48)), 2)

    inflows_today = int(total * 0.004)
    outflows_today = int(total * 0.0035)

    return {
        "liquidity": {
            "cash_position_cents": cash_position,
            "lcr_ratio": lcr,
            "nsfr_ratio": nsfr,
            "fed_funds_rate": 5.33,
            "hqla_cents": hqla,
            "total_deposits_cents": total,
        },
        "cash_flows": {
            "inflows_today_cents": inflows_today,
            "outflows_today_cents": outflows_today,
            "net_position_cents": inflows_today - outflows_today,
        },
        "reserves": {
            "required_reserve_cents": required_reserve,
            "actual_reserve_cents": actual_reserve,
            "excess_reserve_cents": actual_reserve - required_reserve,
        },
        "investments": {
            "securities_portfolio_cents": securities,
            "duration_years": 3.8,
            "unrealized_gain_loss_cents": int(securities * 0.012),
        },
        "alerts": [
            {
                "level": "info",
                "message": f"Total deposit base: ${total / 100_000_000:.2f}B across {customer_count:,} customers",
            }
        ] if lcr >= 1.0 else [
            {
                "level": "warning",
                "message": f"LCR ratio {lcr:.2f}x is below Basel III minimum of 1.0x — review HQLA composition",
            }
        ],
    }


@router.get("/dashboard")
def treasury_dashboard(cu: CurrentUser = Depends(require_permission("treasury:read"))):
    return _get_dashboard_data()


@router.get("/wire-limits")
def wire_limits(cu: CurrentUser = Depends(require_permission("treasury:read"))):
    return {
        "domestic": {
            "daily_limit": "$10,000,000",
            "per_transaction_limit": "$5,000,000",
            "fedwire_cutoff": "5:00 PM ET",
            "ach_cutoff": "10:45 PM ET",
        },
        "international": {
            "daily_limit": "$5,000,000",
            "per_transaction_limit": "$2,000,000",
            "swift_cutoff": "4:30 PM ET",
            "correspondent_bank": "JPMorgan Chase",
        },
        "daily_cutoff_times": {
            "fedwire": "5:00 PM ET",
            "chips": "4:30 PM ET",
            "swift": "4:30 PM ET",
            "ach_same_day": "2:45 PM ET",
        },
    }


@router.get("/positions")
def get_positions(
    position_type: str = None,
    cu: CurrentUser = Depends(require_permission("treasury:read")),
):
    filters, params = ["1=1"], {}
    if position_type:
        filters.append("position_type=:pt")
        params["pt"] = position_type
    with _engine.connect() as c:
        rows = c.execute(
            text(f"SELECT * FROM treasury_positions WHERE {' AND '.join(filters)} ORDER BY market_value DESC"),
            params,
        ).fetchall()
    return {"positions": [dict(r._mapping) for r in rows], "total": len(rows)}


@router.get("/liquidity")
def get_liquidity(cu: CurrentUser = Depends(require_permission("treasury:read"))):
    with _engine.connect() as c:
        rows = c.execute(text("SELECT * FROM liquidity_metrics ORDER BY metric_name")).fetchall()
    return {"metrics": [dict(r._mapping) for r in rows]}


@router.get("/summary")
def treasury_summary(cu: CurrentUser = Depends(require_permission("treasury:read"))):
    data = _get_dashboard_data()
    return {
        "total_portfolio_value": data["investments"]["securities_portfolio_cents"] / 100,
        "cash_position": data["liquidity"]["cash_position_cents"] / 100,
        "lcr_ratio": data["liquidity"]["lcr_ratio"],
        "nsfr_ratio": data["liquidity"]["nsfr_ratio"],
        "active_positions": 0,
        "avg_yield": 0.048,
        "by_type": {},
    }
