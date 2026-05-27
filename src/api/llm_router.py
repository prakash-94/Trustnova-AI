"""
Multi-LLM Router for the Banking AI Copilot.

Provides intelligent task-to-model routing with:
- Task-based model selection (summarization, fraud reasoning, compliance, etc.)
- Retry with exponential backoff (3 retries: 2s → 4s → 8s)
- Fallback chain: primary model → cheaper alternative → GPT-3.5-turbo
- Token cost logger tracking per-call cost to DB

Supported models (configurable via env):
  | Task               | Model               |
  |--------------------|---------------------|
  | Summarization      | Claude 3 Sonnet     |
  | Fraud reasoning    | GPT-4               |
  | Compliance         | Gemini Pro          |
  | PII / Sensitive    | Local Mistral (Ollama) |
  | Simple lookups     | GPT-3.5-turbo       |
  | General / default  | GPT-4               |
"""
import os
import time
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./banking.db")

# --- Model Configuration ---
MODEL_MAP = {
    "summarization": os.getenv("MODEL_SUMMARIZATION", "gpt-4"),
    "fraud_reasoning": os.getenv("MODEL_FRAUD", "gpt-4"),
    "compliance": os.getenv("MODEL_COMPLIANCE", "gpt-4"),
    "sensitive": os.getenv("MODEL_SENSITIVE", "gpt-3.5-turbo"),
    "lookup": os.getenv("MODEL_LOOKUP", "gpt-3.5-turbo"),
    "sentiment": os.getenv("MODEL_SENTIMENT", "gpt-3.5-turbo"),
    "general": os.getenv("MODEL_GENERAL", "gpt-4"),
}

# Fallback chain: try cheaper models if primary fails
FALLBACK_CHAIN = [
    "gpt-4",
    "gpt-3.5-turbo",
]

# Cost per 1K tokens (approximate, USD)
TOKEN_COSTS = {
    "gpt-4": {"input": 0.03, "output": 0.06},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
    "claude-3-sonnet": {"input": 0.003, "output": 0.015},
    "gemini-pro": {"input": 0.00025, "output": 0.0005},
    "mistral-7b": {"input": 0.0, "output": 0.0},  # Local
}

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 2


def _ensure_llm_usage_table():
    """Create the llm_usage table if it doesn't exist."""
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS llm_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_type TEXT NOT NULL,
                model TEXT NOT NULL,
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


def _log_usage(
    task_type: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    latency_ms: float,
    success: bool = True,
    error: str = "",
):
    """Log LLM usage to the database for cost tracking."""
    try:
        engine = create_engine(DATABASE_URL)
        cost_info = TOKEN_COSTS.get(model, {"input": 0.03, "output": 0.06})
        cost_usd = (tokens_in / 1000 * cost_info["input"]) + (tokens_out / 1000 * cost_info["output"])

        with engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO llm_usage 
                (task_type, model, tokens_in, tokens_out, cost_usd, latency_ms, success, error, timestamp)
                VALUES (:task, :model, :tin, :tout, :cost, :latency, :success, :error, :ts)
            """), {
                "task": task_type,
                "model": model,
                "tin": tokens_in,
                "tout": tokens_out,
                "cost": round(cost_usd, 6),
                "latency": latency_ms,
                "success": 1 if success else 0,
                "error": error,
                "ts": datetime.now().isoformat(),
            })
            conn.commit()
    except Exception as e:
        print(f"  [LLM Logger] Failed to log usage: {e}")


def _get_llm(model: str):
    """Get a LangChain LLM instance for the given model name."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set in .env")

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model_name=model,
        temperature=0.1,
        openai_api_key=api_key,
        max_tokens=1024,
    )


def _call_llm_with_retry(model: str, prompt: str) -> Dict[str, Any]:
    """
    Call an LLM with retry and exponential backoff.

    Returns dict with response text, model used, tokens, and latency.
    """
    last_error = None
    backoff = INITIAL_BACKOFF_SECONDS

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            llm = _get_llm(model)
            start = time.time()
            response = llm.invoke(prompt)
            latency_ms = round((time.time() - start) * 1000, 2)

            content = response.content if hasattr(response, "content") else str(response)

            # Extract token usage from response metadata
            usage = getattr(response, "response_metadata", {}).get("token_usage", {})
            tokens_in = usage.get("prompt_tokens", len(prompt) // 4)
            tokens_out = usage.get("completion_tokens", len(content) // 4)

            return {
                "response": content,
                "model_used": model,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "latency_ms": latency_ms,
                "attempt": attempt,
            }

        except Exception as e:
            last_error = str(e)
            print(f"  [LLM Router] Attempt {attempt}/{MAX_RETRIES} failed for {model}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(backoff)
                backoff *= 2

    raise RuntimeError(f"All {MAX_RETRIES} attempts failed for {model}: {last_error}")


def route(task_type: str, prompt: str) -> Dict[str, Any]:
    """
    Route a prompt to the appropriate LLM based on task type.

    Implements the full routing pipeline:
    1. Select model based on task_type
    2. Try primary model with retry + backoff
    3. If all retries fail, try fallback models
    4. Log usage to database

    Args:
        task_type: One of 'summarization', 'fraud_reasoning', 'compliance',
                   'sensitive', 'lookup', 'sentiment', 'general'
        prompt: The prompt string to send to the LLM

    Returns:
        Dict with keys: response, model_used, latency_ms, tokens_in, tokens_out
    """
    _ensure_llm_usage_table()

    primary_model = MODEL_MAP.get(task_type, MODEL_MAP["general"])

    # Try primary model first
    try:
        result = _call_llm_with_retry(primary_model, prompt)

        _log_usage(
            task_type=task_type,
            model=result["model_used"],
            tokens_in=result["tokens_in"],
            tokens_out=result["tokens_out"],
            latency_ms=result["latency_ms"],
        )

        return result

    except RuntimeError as primary_error:
        print(f"  [LLM Router] Primary model '{primary_model}' exhausted. Trying fallbacks...")

        # Try fallback chain
        for fallback_model in FALLBACK_CHAIN:
            if fallback_model == primary_model:
                continue  # Skip the one that already failed

            try:
                result = _call_llm_with_retry(fallback_model, prompt)

                _log_usage(
                    task_type=task_type,
                    model=result["model_used"],
                    tokens_in=result["tokens_in"],
                    tokens_out=result["tokens_out"],
                    latency_ms=result["latency_ms"],
                )

                print(f"  [LLM Router] Fallback to '{fallback_model}' succeeded.")
                return result

            except RuntimeError:
                continue

        # All models failed
        _log_usage(
            task_type=task_type,
            model=primary_model,
            tokens_in=0,
            tokens_out=0,
            latency_ms=0,
            success=False,
            error=str(primary_error),
        )

        raise RuntimeError(
            f"All LLM models failed for task '{task_type}'. "
            f"Primary: {primary_model}, Fallbacks: {FALLBACK_CHAIN}"
        )


def get_usage_summary(days: int = 30) -> Dict:
    """Get LLM usage summary for the last N days."""
    engine = create_engine(DATABASE_URL)
    try:
        df = __import__("pandas").read_sql(
            f"SELECT * FROM llm_usage ORDER BY timestamp DESC LIMIT 1000",
            engine,
        )

        if df.empty:
            return {"total_calls": 0, "total_cost_usd": 0.0}

        return {
            "total_calls": len(df),
            "total_cost_usd": round(df["cost_usd"].sum(), 4),
            "by_model": df.groupby("model").agg(
                calls=("id", "count"),
                total_tokens=("tokens_in", "sum"),
                avg_latency_ms=("latency_ms", "mean"),
                cost_usd=("cost_usd", "sum"),
            ).to_dict(orient="index"),
            "by_task": df.groupby("task_type").agg(
                calls=("id", "count"),
                cost_usd=("cost_usd", "sum"),
            ).to_dict(orient="index"),
            "error_rate": round(1 - df["success"].mean(), 4),
        }

    except Exception as e:
        return {"error": str(e)}


# --- CLI ---
if __name__ == "__main__":
    _ensure_llm_usage_table()
    print("LLM Router — Quick Test")
    print("=" * 50)

    result = route("general", "What is 2 + 2? Answer in one word.")
    print(f"  Model:   {result['model_used']}")
    print(f"  Latency: {result['latency_ms']}ms")
    print(f"  Answer:  {result['response']}")

    print("\nUsage Summary:")
    summary = get_usage_summary()
    for k, v in summary.items():
        print(f"  {k}: {v}")
