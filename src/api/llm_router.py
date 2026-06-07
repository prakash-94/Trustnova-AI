"""
Multi-LLM Router for the Banking AI Copilot.

Supports two providers (selected via LLM_PROVIDER env var):
  groq   — Groq Cloud (default, fastest). Model: llama-3.3-70b-versatile
  openai — OpenAI GPT-4 / GPT-3.5-turbo (fallback)

Features:
  - Task-based model routing (summarization, fraud, compliance, etc.)
  - Retry with exponential backoff (3 attempts: 2s → 4s → 8s)
  - Provider-aware fallback chain
  - Token cost logging to DB
"""
import os
import time
from datetime import datetime
from typing import Dict, Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL  = os.getenv("DATABASE_URL", "sqlite:///./banking.db")
LLM_PROVIDER  = os.getenv("LLM_PROVIDER", "groq").lower().strip()

# ── Model names per provider ───────────────────────────────────
# Groq: llama-3.3-70b-versatile is the top model — 128K ctx, fast
GROQ_MODEL    = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
OPENAI_MODELS = {
    "fast":    os.getenv("OPENAI_MODEL_FAST",    "gpt-3.5-turbo"),
    "capable": os.getenv("OPENAI_MODEL_CAPABLE", "gpt-4"),
}

# ── Task → model mapping ───────────────────────────────────────
# Groq uses one model for everything (it's fast + capable enough).
# OpenAI routes heavy tasks to GPT-4, light tasks to GPT-3.5-turbo.
def _build_model_map():
    if LLM_PROVIDER == "groq":
        return {k: GROQ_MODEL for k in
                ["summarization", "fraud_reasoning", "compliance",
                 "sensitive", "lookup", "sentiment", "general"]}
    # OpenAI routing
    return {
        "summarization":   os.getenv("MODEL_SUMMARIZATION", OPENAI_MODELS["capable"]),
        "fraud_reasoning": os.getenv("MODEL_FRAUD",         OPENAI_MODELS["capable"]),
        "compliance":      os.getenv("MODEL_COMPLIANCE",    OPENAI_MODELS["capable"]),
        "sensitive":       os.getenv("MODEL_SENSITIVE",     OPENAI_MODELS["fast"]),
        "lookup":          os.getenv("MODEL_LOOKUP",        OPENAI_MODELS["fast"]),
        "sentiment":       os.getenv("MODEL_SENTIMENT",     OPENAI_MODELS["fast"]),
        "general":         os.getenv("MODEL_GENERAL",       OPENAI_MODELS["capable"]),
    }

MODEL_MAP = _build_model_map()

# Fallback chain (provider-aware)
FALLBACK_CHAIN = (
    [GROQ_MODEL, OPENAI_MODELS["capable"], OPENAI_MODELS["fast"]]
    if LLM_PROVIDER == "groq"
    else [OPENAI_MODELS["capable"], OPENAI_MODELS["fast"]]
)

# Cost per 1K tokens (USD). Groq charges near-zero for Llama models.
TOKEN_COSTS = {
    GROQ_MODEL:                  {"input": 0.00005, "output": 0.00008},
    "llama-3.1-70b-versatile":   {"input": 0.00005, "output": 0.00008},
    "llama-3.1-8b-instant":      {"input": 0.00001, "output": 0.00001},
    "gpt-4":                     {"input": 0.03,    "output": 0.06},
    "gpt-4-turbo":               {"input": 0.01,    "output": 0.03},
    "gpt-3.5-turbo":             {"input": 0.0005,  "output": 0.0015},
}

MAX_RETRIES           = 3
INITIAL_BACKOFF_SECS  = 2


# ── DB helpers ─────────────────────────────────────────────────
def _ensure_llm_usage_table():
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS llm_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT NOT NULL,
                model TEXT NOT NULL,
                provider TEXT,
                tokens_in INTEGER,
                tokens_out INTEGER,
                cost_usd REAL,
                latency_ms REAL,
                success INTEGER DEFAULT 1,
                error TEXT,
                timestamp TEXT NOT NULL
            )
        """))
        conn.commit()


def _log_usage(task_type, model, tokens_in, tokens_out, latency_ms,
               success=True, error=""):
    try:
        engine = create_engine(DATABASE_URL)
        c = TOKEN_COSTS.get(model, {"input": 0.03, "output": 0.06})
        cost = (tokens_in / 1000 * c["input"]) + (tokens_out / 1000 * c["output"])
        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO llm_usage
                (task_type, model, provider, tokens_in, tokens_out, cost_usd,
                 latency_ms, success, error, timestamp)
                VALUES (:task, :model, :provider, :tin, :tout, :cost,
                        :lat, :ok, :err, :ts)
            """), {
                "task": task_type, "model": model, "provider": LLM_PROVIDER,
                "tin": tokens_in, "tout": tokens_out, "cost": round(cost, 8),
                "lat": latency_ms, "ok": 1 if success else 0,
                "err": error, "ts": datetime.now().isoformat(),
            })
            conn.commit()
    except Exception as e:
        print(f"  [LLM Logger] {e}")


# ── LLM factory ───────────────────────────────────────────────
def _get_llm(model: str):
    """Return a LangChain chat model for the given model name."""
    # Groq models
    if LLM_PROVIDER == "groq" or model == GROQ_MODEL or "llama" in model.lower() or "mixtral" in model.lower() or "gemma" in model.lower():
        groq_key = os.getenv("GROQ_API_KEY")
        if not groq_key:
            raise ValueError("GROQ_API_KEY not set in .env")
        from langchain_groq import ChatGroq
        return ChatGroq(
            model=model,
            temperature=0.1,
            groq_api_key=groq_key,
            max_tokens=2048,
        )

    # OpenAI models
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        raise ValueError("OPENAI_API_KEY not set in .env")
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model_name=model,
        temperature=0.1,
        openai_api_key=openai_key,
        max_tokens=2048,
    )


# ── Retry wrapper ──────────────────────────────────────────────
def _call_with_retry(model: str, prompt: str) -> Dict[str, Any]:
    last_err = None
    backoff   = INITIAL_BACKOFF_SECS

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            llm    = _get_llm(model)
            t0     = time.time()
            resp   = llm.invoke(prompt)
            latency = round((time.time() - t0) * 1000, 2)

            content = resp.content if hasattr(resp, "content") else str(resp)
            usage   = getattr(resp, "response_metadata", {}).get("token_usage",
                      getattr(resp, "usage_metadata", {}))
            tin     = usage.get("prompt_tokens",     usage.get("input_tokens",  len(prompt)  // 4))
            tout    = usage.get("completion_tokens",  usage.get("output_tokens", len(content) // 4))

            return {
                "response":   content,
                "model_used": model,
                "provider":   LLM_PROVIDER,
                "tokens_in":  tin,
                "tokens_out": tout,
                "latency_ms": latency,
                "attempt":    attempt,
            }
        except Exception as e:
            last_err = str(e)
            print(f"  [LLM Router] attempt {attempt}/{MAX_RETRIES} '{model}': {e}")
            if attempt < MAX_RETRIES:
                time.sleep(backoff)
                backoff *= 2

    raise RuntimeError(f"All {MAX_RETRIES} attempts failed for {model}: {last_err}")


# ── Public API ─────────────────────────────────────────────────
def route(task_type: str, prompt: str) -> Dict[str, Any]:
    """
    Route a prompt to the right LLM based on task type.

    Args:
        task_type: 'summarization' | 'fraud_reasoning' | 'compliance' |
                   'sensitive' | 'lookup' | 'sentiment' | 'general'
        prompt:    Prompt string

    Returns:
        Dict: response, model_used, provider, latency_ms, tokens_in, tokens_out
    """
    _ensure_llm_usage_table()
    primary = MODEL_MAP.get(task_type, MODEL_MAP["general"])

    try:
        result = _call_with_retry(primary, prompt)
        _log_usage(task_type, result["model_used"],
                   result["tokens_in"], result["tokens_out"], result["latency_ms"])
        return result

    except RuntimeError as primary_err:
        print(f"  [LLM Router] '{primary}' exhausted — trying fallbacks…")
        for fb in FALLBACK_CHAIN:
            if fb == primary:
                continue
            try:
                result = _call_with_retry(fb, prompt)
                _log_usage(task_type, result["model_used"],
                           result["tokens_in"], result["tokens_out"], result["latency_ms"])
                print(f"  [LLM Router] Fallback '{fb}' succeeded.")
                return result
            except RuntimeError:
                continue

        _log_usage(task_type, primary, 0, 0, 0,
                   success=False, error=str(primary_err))
        raise RuntimeError(
            f"All LLM models failed for task '{task_type}'. "
            f"Provider: {LLM_PROVIDER}, Primary: {primary}"
        )


def get_usage_summary(days: int = 30) -> Dict:
    """LLM cost + usage summary for the last N days."""
    try:
        import pandas as pd
        engine = create_engine(DATABASE_URL)
        df = pd.read_sql("SELECT * FROM llm_usage ORDER BY timestamp DESC LIMIT 1000", engine)
        if df.empty:
            return {"total_calls": 0, "total_cost_usd": 0.0}
        return {
            "total_calls":    len(df),
            "total_cost_usd": round(df["cost_usd"].sum(), 6),
            "provider":       LLM_PROVIDER,
            "primary_model":  MODEL_MAP["general"],
            "by_model": df.groupby("model").agg(
                calls=("id", "count"),
                avg_latency_ms=("latency_ms", "mean"),
                cost_usd=("cost_usd", "sum"),
            ).round(4).to_dict(orient="index"),
            "by_task": df.groupby("task_type").agg(
                calls=("id", "count"),
                cost_usd=("cost_usd", "sum"),
            ).round(6).to_dict(orient="index"),
            "error_rate": round(1 - df["success"].mean(), 4),
        }
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    _ensure_llm_usage_table()
    print(f"LLM Router — provider={LLM_PROVIDER}, model={MODEL_MAP['general']}")
    print("=" * 60)
    result = route("general", "Reply with exactly three words: 'Groq is fast'.")
    print(f"  Model:    {result['model_used']}")
    print(f"  Provider: {result['provider']}")
    print(f"  Latency:  {result['latency_ms']}ms")
    print(f"  Response: {result['response']}")
