"""The plain-Python rules about IBM AML files: names, identifiers and the patterns-file parser."""

import pytest

from trustnova_lake.ibm import (
    PatternFormatError,
    account_id,
    bank_country,
    entity_type,
    file_prefix,
    normalize_bank_id,
    parse_file_name,
    parse_patterns,
    parse_variants,
    pattern_rows,
)

LINE = "2022/09/01 00:06,021174,800737690,012,80011F990,2848.96,Euro,2848.96,Euro,ACH,1"


@pytest.mark.parametrize("name, expected", [
    ("HI-Small_Trans.csv", ("HIS", "Trans")),
    ("LI-Medium_Patterns.txt", ("LIM", "Patterns")),
    ("HI-Large_accounts.csv", ("HIL", "accounts")),
    ("HI-Large_Trans.part-003.csv", ("HIL", "Trans")),
])
def test_file_names_map_to_a_variant(name, expected):
    assert parse_file_name(name) == expected


@pytest.mark.parametrize("name", ["HI-Large_Trans.manifest.json", "HI-Tiny_Trans.csv", "notes.txt", "HI-Small_Trans.csv.bak"])
def test_other_files_are_rejected(name):
    with pytest.raises(ValueError):
        parse_file_name(name)


def test_variants_are_parsed_and_checked():
    assert parse_variants(" his, LIS ,his") == ["HIS", "LIS"]
    assert file_prefix("LIL") == "LI-Large"
    with pytest.raises(ValueError):
        parse_variants("HIS,XYZ")
    with pytest.raises(ValueError):
        parse_variants(" , ")


@pytest.mark.parametrize("raw, expected", [("010", "10"), ("03208", "3208"), ("021174", "21174"), ("0", "0"), ("000", "0"), ("10", "10")])
def test_bank_ids_lose_their_leading_zeros(raw, expected):
    assert normalize_bank_id(raw) == expected


def test_account_ids_carry_variant_and_bank():
    assert account_id("HIS", "010", "8000EBD30") == "HIS:10:8000EBD30"
    assert account_id("HIS", "012", "8000EBD30") != account_id("HIS", "010", "8000EBD30")
    assert account_id("LIS", "010", "8000EBD30") != account_id("HIS", "010", "8000EBD30")
    with pytest.raises(ValueError):
        normalize_bank_id("01A")


def test_entity_type_and_bank_country():
    assert entity_type("Sole Proprietorship #50438") == "Sole Proprietorship"
    assert entity_type("Corporation #889") == "Corporation"
    assert bank_country("Germany Bank #4815") == "Germany"
    assert bank_country("UK Bank #33") == "UK"
    assert bank_country("Crytpo Bank #12") is None
    assert bank_country("National Bank of Harrisburg") is None


def test_patterns_are_split_into_attempts():
    text = (f"BEGIN LAUNDERING ATTEMPT - FAN-OUT:  Max 16-degree Fan-Out\n{LINE}\n{LINE}\n"
            "END LAUNDERING ATTEMPT - FAN-OUT\n\n"
            f"BEGIN LAUNDERING ATTEMPT - STACK\n{LINE}\nEND LAUNDERING ATTEMPT - STACK\n")
    attempts = parse_patterns(text)
    assert [(a.seq, a.pattern_type, a.detail, len(a.lines)) for a in attempts] == [
        (1, "FAN-OUT", "Max 16-degree Fan-Out", 2), (2, "STACK", "", 1)]
    rows = pattern_rows("HIS", text)
    assert rows[0][:5] == ("HIS", "HIS-P00001", "FAN-OUT", "Max 16-degree Fan-Out", "1")
    assert rows[2][1] == "HIS-P00002" and len(rows[0]) == 16


@pytest.mark.parametrize("text, problem", [
    (f"{LINE}\n", "outside"),
    (f"BEGIN LAUNDERING ATTEMPT - CYCLE:  Max 3 hops\n{LINE}\n", "ends inside"),
    (f"BEGIN LAUNDERING ATTEMPT - CYCLE: x\n{LINE}\nEND LAUNDERING ATTEMPT - FAN-IN\n", "without a matching BEGIN"),
    ("BEGIN LAUNDERING ATTEMPT - CYCLE: x\nBEGIN LAUNDERING ATTEMPT - CYCLE: y\n", "unfinished"),
    ("BEGIN LAUNDERING ATTEMPT - SMURFING: x\nEND LAUNDERING ATTEMPT - SMURFING\n", "unknown pattern type"),
    ("BEGIN LAUNDERING ATTEMPT - CYCLE: x\n2022/09/01 00:06,1,2\nEND LAUNDERING ATTEMPT - CYCLE\n", "fields"),
])
def test_damaged_pattern_files_fail_loudly(text, problem):
    with pytest.raises(PatternFormatError, match=problem):
        parse_patterns(text)


def test_a_changed_schema_recreates_the_table_only_when_every_simulation_is_rewritten():
    from trustnova_lake.jobs import schema_change_action

    old = [("variant", "string"), ("a", "double")]
    new = [*old, ("b", "double")]
    assert schema_change_action(old, old, ["HIS", "LIS"], ["HIS"]) == "overwrite"
    assert schema_change_action(old, new, ["HIS", "LIS"], ["HIS", "LIS"]) == "recreate"
    assert schema_change_action(old, new, [], ["HIS"]) == "recreate"
    with pytest.raises(ValueError, match="LIS"):
        schema_change_action(old, new, ["HIS", "LIS"], ["HIS"])
