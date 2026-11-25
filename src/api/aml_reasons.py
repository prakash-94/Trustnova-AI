"""Turn the ML model's reason codes into sentences an AML analyst can read.

Each alert stores its top reasons as `{"feature": ..., "value": ..., "contribution": ...}` (see
`trustnova_ml.train.top_reasons`). The feature names are short codes such as `s_p7_ach_new_out`; this module
spells them out ("Sender: ACH payments to new accounts in the previous 7 days: 12"). It only describes what the
model saw. It never adds facts of its own.
"""
from __future__ import annotations

import math

PAYMENT_FORMATS = ("ACH", "Bitcoin", "Cash", "Cheque", "Credit Card", "Reinvestment", "Wire")
ENTITY_TYPES = ("Individual", "Sole Proprietorship", "Partnership", "Corporation", "Country", "Direct")

_SIDES = {
    "so_": "Sender's owner (all accounts)",
    "ro_": "Receiver's owner (all accounts)",
    "s_": "Sender",
    "r_": "Receiver",
}
_WINDOWS = {"d0": "earlier today", "p1": "the previous day", "p7": "the previous 7 days", "p28": "the previous 28 days"}
_METRICS = {
    "n_out": ("payments sent", "count"), "n_in": ("payments received", "count"),
    "usd_out": ("money sent", "usd"), "usd_in": ("money received", "usd"),
    "cp_out": ("different accounts paid", "count"), "cp_in": ("different accounts paying in", "count"),
    "band_out": ("payments sent between $7,000 and $10,000", "count"),
    "band_in": ("payments received between $7,000 and $10,000", "count"),
    "cash_out": ("cash payments sent", "count"), "crypto_out": ("Bitcoin payments sent", "count"),
    "usd_out_sq": ("spread of amounts sent", "raw"), "usd_in_sq": ("spread of amounts received", "raw"),
    "new_cp_out": ("payments to accounts never paid before", "count"),
    "new_cp_in": ("payments from accounts never seen before", "count"),
    "ach_out": ("ACH payments sent", "count"), "ach_in": ("ACH payments received", "count"),
    "ach_new_out": ("ACH payments to new accounts", "count"),
    "ach_new_in": ("ACH payments from new accounts", "count"),
}
_SIDE_SINGLE = {
    "account_age_days": ("account age in days", "count"),
    "amount_z_28d": ("how unusual this amount is against its last 28 days (z-score)", "num"),
    "burst_vs_28d": ("activity today against its normal daily rate", "times"),
    "new_cp_share_7d": ("share of counterparties that are new (7 days)", "pct"),
    "format_first": ("first time using this payment format", "flag"),
    "minutes_since_in": ("minutes since money last arrived", "minutes"),
    "vs_inflow_24h": ("this payment as a multiple of what it received in the last day", "times"),
    "owner_n_accounts": ("accounts held by the owner", "count"),
    "owner_n_banks": ("banks used by the owner", "count"),
    "n_accounts_active_7d": ("accounts active in the last 7 days", "count"),
}
_TXN = {
    "currency_change": "The currency changed during the payment",
    "cross_bank": "The payment went to a different bank",
    "is_self_transfer": "The payment moved money between accounts of the same owner",
    "in_band": "The amount is between $7,000 and $10,000 (just under the reporting threshold)",
    "round_amount": "The amount is a round number",
    "first_time_pair": "It is the first ever payment between these two accounts",
    "closes_3cycle_7d": "It closes a 3-step loop of money within 7 days",
    "pt_chain_returns": "The chain of matching payments started at this payment's receiver: the money is going back home",
}


def _fmt(value: float, kind: str) -> str:
    if kind == "usd":
        return f"${value:,.0f}"
    if kind == "count":
        return f"{value:,.0f}"
    if kind == "pct":
        return f"{100 * value:.0f}%"
    if kind == "flag":
        return "yes" if value >= 0.5 else "no"
    if kind == "times":
        return f"×{value:,.1f}"
    if kind == "minutes":
        return "never" if value < 0 else f"{value:,.0f}"
    return f"{value:,.2f}"


def _txn_reason(f: str, v: float) -> str | None:
    if f == "log_amount_usd":
        return f"Payment amount: ${math.expm1(v):,.0f}"
    if f == "payment_format_code":
        i = int(v)
        return f"Paid by {PAYMENT_FORMATS[i]}" if 0 <= i < len(PAYMENT_FORMATS) else "Unusual payment format"
    if f in _TXN:
        return _TXN[f] if v >= 0.5 else f"Not the case: {_TXN[f][0].lower()}{_TXN[f][1:]}"
    if f == "hour":
        return f"Hour of day: {int(v)}:00"
    if f == "weekday":
        return f"Day of week: {int(v)}"
    if f == "reverse_n_7d":
        return f"Payments in the opposite direction between these two accounts in the last 7 days: {v:,.0f}"
    if f == "reverse_usd_7d":
        return f"Money sent back the other way between these two accounts in the last 7 days: ${v:,.0f}"
    if f == "pt_match_5pct":
        return f"Payments received in the last 7 days within 5% of this amount: {v:,.0f}"
    if f == "pt_match_20pct":
        return f"Payments received in the last 7 days within 20% of this amount: {v:,.0f}"
    if f == "pt_best_gap":
        if v >= 1:
            return "No recent incoming payment with a similar amount"
        return f"The amount matches money the sender just received (difference {100 * v:.1f}%)"
    if f == "pt_minutes_since_match":
        return "No matching incoming payment" if v < 0 else f"Minutes since the matching money arrived: {v:,.0f}"
    if f == "pt_chain_len":
        return f"The money was passed along a chain of {v:,.0f} payments with matching amounts"
    return None


def _side_reason(f: str, v: float) -> str | None:
    for prefix, who in _SIDES.items():
        if not f.startswith(prefix):
            continue
        rest = f[len(prefix):]
        if rest == "entity_type_code":
            i = int(v)
            return f"{who}: owner type {ENTITY_TYPES[i] if 0 <= i < len(ENTITY_TYPES) else 'unknown'}"
        if rest in _SIDE_SINGLE:
            label, kind = _SIDE_SINGLE[rest]
            return f"{who}: {label}: {_fmt(v, kind)}"
        window, _, metric = rest.partition("_")
        if window in _WINDOWS and metric in _METRICS:
            label, kind = _METRICS[metric]
            return f"{who}: {label} in {_WINDOWS[window]}: {_fmt(v, kind)}"
        return None
    return None


def explain(reason: dict) -> str:
    """One reason code as a sentence. Unknown codes fall back to `name = value`, never to a guess."""
    f, v = str(reason.get("feature", "")), float(reason.get("value", 0) or 0)
    return _txn_reason(f, v) or _side_reason(f, v) or f"{f} = {v:,.2f}"
