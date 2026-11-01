"""Facts about the IBM Transactions for AML files, measured on the real data before any transform was written.

Bank ids are zero-padded in *_Trans.csv / *_Patterns.txt ("010") but not in *_accounts.csv ("10"); stripping the
leading zeros makes all of them match. Account numbers collide across banks, and the six simulations reuse
numbers, so every id carries the simulation (variant) and the bank.
"""

import re
from dataclasses import dataclass, field

VARIANTS: dict[str, str] = {
    "HI-Small": "HIS", "HI-Medium": "HIM", "HI-Large": "HIL",
    "LI-Small": "LIS", "LI-Medium": "LIM", "LI-Large": "LIL",
}
VARIANT_CODES = tuple(VARIANTS.values())

# Column names for *_Trans.csv (its header repeats "Account", so the files are read with these names instead).
RAW_TRANSACTION_COLUMNS = (
    "timestamp", "from_bank", "from_account", "to_bank", "to_account",
    "amount_received", "receiving_currency", "amount_paid", "payment_currency", "payment_format", "is_laundering",
)
RAW_ACCOUNT_COLUMNS = ("bank_name", "bank_id", "account_number", "entity_id", "entity_name")
PATTERN_TYPES = ("FAN-OUT", "FAN-IN", "CYCLE", "GATHER-SCATTER", "SCATTER-GATHER", "STACK", "BIPARTITE", "RANDOM")

# Large files are stored as <name>.part-NNN.csv because the Files API caps an upload at 5 GiB.
_FILE_RE = re.compile(
    r"^(?P<prefix>(?:HI|LI)-(?:Small|Medium|Large))_(?P<kind>Trans|Patterns|accounts)"
    r"(?:\.part-\d{3})?\.(?:csv|txt)$"
)
_BANK_COUNTRY_RE = re.compile(r"^(?P<country>.+?) Bank #\d+$")
_ENTITY_SUFFIX_RE = re.compile(r"\s*#\d+$")
NOT_A_COUNTRY = {"Crytpo"}  # the dataset's spelling of its crypto-exchange banks


def parse_file_name(name: str) -> tuple[str, str]:
    """`HI-Large_Trans.part-002.csv` -> ("HIL", "Trans"). Raises ValueError for anything else."""
    m = _FILE_RE.match(name)
    if not m:
        raise ValueError(f"not an IBM AML file name: {name!r}")
    return VARIANTS[m.group("prefix")], m.group("kind")


def file_prefix(variant: str) -> str:
    """"HIL" -> "HI-Large"."""
    for prefix, code in VARIANTS.items():
        if code == variant:
            return prefix
    raise ValueError(f"unknown variant {variant!r}; expected one of {VARIANT_CODES}")


def parse_variants(text: str) -> list[str]:
    """"HIS, lis" -> ["HIS", "LIS"]; rejects unknown codes and empty input."""
    codes = [c.strip().upper() for c in text.split(",") if c.strip()]
    if not codes:
        raise ValueError("no variants given")
    for c in codes:
        file_prefix(c)
    return list(dict.fromkeys(codes))


def normalize_bank_id(raw: str) -> str:
    """"010" -> "10", "000" -> "0". The Spark transform uses the same rule (see transforms.BANK_ZEROS)."""
    if not raw.isdigit():
        raise ValueError(f"bank id must be digits: {raw!r}")
    return str(int(raw))


def account_id(variant: str, bank: str, account: str) -> str:
    return f"{variant}:{normalize_bank_id(bank)}:{account}"


def entity_key(variant: str, entity: str) -> str:
    return f"{variant}:{entity}"


def entity_type(entity_name: str) -> str:
    """"Corporation #33520" -> "Corporation"."""
    return _ENTITY_SUFFIX_RE.sub("", entity_name).strip()


def bank_country(bank_name: str) -> str | None:
    """"Germany Bank #4815" -> "Germany"; crypto exchanges and named banks ("National Bank of X") -> None."""
    m = _BANK_COUNTRY_RE.match(bank_name)
    if not m or m.group("country") in NOT_A_COUNTRY:
        return None
    return m.group("country")


class PatternFormatError(ValueError):
    """The patterns file broke the BEGIN ... END block structure."""


@dataclass
class PatternAttempt:
    seq: int
    pattern_type: str
    detail: str
    lines: list[str] = field(default_factory=list)


_BEGIN_RE = re.compile(r"^BEGIN LAUNDERING ATTEMPT - (?P<type>[A-Z\-]+):?\s*(?P<detail>.*)$")
_END_RE = re.compile(r"^END LAUNDERING ATTEMPT - (?P<type>[A-Z\-]+)\s*$")


def parse_patterns(text: str) -> list[PatternAttempt]:
    """Split a *_Patterns.txt file into attempts. Blank lines separate attempts; every other line must be inside a
    BEGIN/END pair of the same type, so a damaged file fails loudly instead of losing ground truth."""
    attempts: list[PatternAttempt] = []
    current: PatternAttempt | None = None
    for line_no, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        begin, end = _BEGIN_RE.match(line), _END_RE.match(line)
        if begin:
            if current is not None:
                raise PatternFormatError(f"line {line_no}: BEGIN inside an unfinished {current.pattern_type} block")
            if begin.group("type") not in PATTERN_TYPES:
                raise PatternFormatError(f"line {line_no}: unknown pattern type {begin.group('type')!r}")
            current = PatternAttempt(len(attempts) + 1, begin.group("type"), begin.group("detail").strip())
            attempts.append(current)
        elif end:
            if current is None or end.group("type") != current.pattern_type:
                raise PatternFormatError(f"line {line_no}: END without a matching BEGIN")
            current = None
        else:
            if current is None:
                raise PatternFormatError(f"line {line_no}: transaction line outside a laundering attempt")
            if len(line.split(",")) != len(RAW_TRANSACTION_COLUMNS):
                raise PatternFormatError(f"line {line_no}: expected {len(RAW_TRANSACTION_COLUMNS)} fields")
            current.lines.append(line)
    if current is not None:
        raise PatternFormatError(f"file ends inside a {current.pattern_type} block")
    return attempts


PATTERN_ROW_COLUMNS = ("variant", "attempt_id", "pattern_type", "pattern_detail", "attempt_line", *RAW_TRANSACTION_COLUMNS)


def pattern_rows(variant: str, text: str) -> list[tuple[str, ...]]:
    """One row per transaction line: variant, attempt_id ("HIS-P00001"), type, detail, line within the attempt, then
    the 11 raw fields, ready to be typed exactly like *_Trans.csv rows."""
    rows = []
    for a in parse_patterns(text):
        attempt_id = f"{variant}-P{a.seq:05d}"
        for i, line in enumerate(a.lines, start=1):
            rows.append((variant, attempt_id, a.pattern_type, a.detail, str(i), *line.split(",")))
    return rows
