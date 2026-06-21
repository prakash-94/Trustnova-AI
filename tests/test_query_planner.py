from src.rag.intent_classifier import classify_intent, classify_intents, needs_graph_context, plan_intents


def test_legacy_classifier_keeps_first_intent():
    assert classify_intent("show high risk customers") == "risk"


def test_compound_query_returns_multiple_intents():
    intents = classify_intents("Show this customer's recent transactions and fraud alerts")
    assert "fraud" in intents
    assert "customer" in intents
    assert "transaction" in intents


def test_graph_context_for_multi_hop_customer_question():
    query = "Explain why this customer's transactions and loans create fraud risk"
    assert needs_graph_context(query, customer_id="cust-1")
    assert plan_intents(query, customer_id="cust-1")[0] == "customer"


def test_simple_policy_question_does_not_request_graph():
    assert not needs_graph_context("What is the wire transfer policy?")
    assert plan_intents("What is the wire transfer policy?") == ["general"]


def test_highest_customer_loan_routes_to_live_loan_data():
    query = "Which customer has the highest loan amount?"
    assert classify_intents(query) == ["loan"]
    assert plan_intents(query) == ["loan"]
