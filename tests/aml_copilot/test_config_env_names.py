"""AML Copilot shares a process and a .env with TrustNova, whose LLM_PROVIDER / LLM_MODEL name the chat LLM.
The AML model settings must read only their AML_-prefixed variables, and still accept field names as arguments."""

import pytest

from aml_copilot.config import Settings


@pytest.fixture
def trustnova_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("LLM_MODEL", "llama-3.3-70b-versatile")
    for name in ("TYPOLOGY_MODEL", "NARRATIVE_MODEL", "FAITHFULNESS_MODEL"):
        monkeypatch.setenv(name, "not-an-aml-model")
    for name in ("AML_LLM_PROVIDER", "AML_LLM_MODEL", "AML_TYPOLOGY_MODEL", "AML_NARRATIVE_MODEL",
                 "AML_FAITHFULNESS_MODEL", "ANTHROPIC_MODEL"):
        monkeypatch.delenv(name, raising=False)


def test_trustnova_llm_variables_are_ignored(trustnova_env):
    s = Settings(_env_file=None)
    assert (s.llm_provider, s.llm_model) == ("gemini", "gemini-3.5-flash")
    assert (s.typology_model, s.narrative_model, s.faithfulness_model) == ("", "", "")


def test_the_aml_prefixed_variables_are_read(trustnova_env, monkeypatch):
    monkeypatch.setenv("AML_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("AML_LLM_MODEL", "claude-haiku-4-5")
    monkeypatch.setenv("AML_TYPOLOGY_MODEL", "claude-sonnet-5")
    monkeypatch.setenv("AML_NARRATIVE_MODEL", "claude-sonnet-5")
    monkeypatch.setenv("AML_FAITHFULNESS_MODEL", "claude-sonnet-5")
    s = Settings(_env_file=None)
    assert (s.llm_provider, s.llm_model) == ("anthropic", "claude-haiku-4-5")
    assert s.typology_model == s.narrative_model == s.faithfulness_model == "claude-sonnet-5"


def test_field_name_arguments_still_work_and_win_over_the_environment(trustnova_env, monkeypatch):
    monkeypatch.setenv("AML_LLM_PROVIDER", "anthropic")
    s = Settings(_env_file=None, llm_provider="vertex", llm_model="m1", typology_model="m2")
    assert (s.llm_provider, s.llm_model, s.typology_model) == ("vertex", "m1", "m2")
    assert Settings(_env_file=None, anthropic_model="claude-sonnet-5").llm_model == "claude-sonnet-5"


def test_model_copy_updates_by_field_name(trustnova_env):
    s = Settings(_env_file=None).model_copy(update={"faithfulness_model": "claude-haiku-4-5"})
    assert s.faithfulness_model == "claude-haiku-4-5"
