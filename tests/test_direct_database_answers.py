from src.agents.base_agent import _direct_structured_answer


def test_extracts_authoritative_database_answer():
    context = """[STRUCTURED INTENT: LOAN]
=== LOAN PORTFOLIO ===
ANSWER: Melissa Hunter has the highest original loan amount: $499,323.00.
Data source: loans table
"""
    assert _direct_structured_answer(context) == (
        "Melissa Hunter has the highest original loan amount: $499,323.00."
    )


def test_normal_structured_context_still_uses_llm():
    assert _direct_structured_answer("Customer records without a deterministic answer") is None
