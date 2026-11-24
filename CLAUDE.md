# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

One product made of four codebases that are being merged (plan and status: `docs/AML_INTEGRATION_PLAN.md`, the source of truth for phases, decisions and ML results):

| Path | What | Packaged? |
|---|---|---|
| `src/` | TrustNova FastAPI backend (13-role RBAC, RAG copilot, trust scores, banking routes) on SQLite `banking.db` | No — runs from the repo root |
| `frontend-react/` | React 18 + TypeScript + Vite UI | npm |
| `aml_copilot/` | AML investigation copilot merged in from a separate repo (LangGraph: evidence → typology RAG → SAR narrative → faithfulness check) | Yes |
| `trustnova_lake/` | IBM AML dataset lakehouse on Databricks (bronze → silver → gold) | Yes |
| `trustnova_ml/` | ML detection: point-in-time features, LightGBM M1 (transaction risk) / M3 (pattern type), evaluation gate, batch scoring | Yes |

`pyproject.toml` builds one wheel (`aml_copilot`, `trustnova_lake`, `trustnova_ml`) that the Databricks jobs install; dependencies are pinned in the `requirements*.txt` files and the bundle's job environments, not in `pyproject.toml`.

## Commands

Python 3.11+. Use the repo's `.venv` (on Windows: `.venv/Scripts/python.exe`); it has lightgbm, mlflow, pyspark and the Databricks SDK.

```bash
# Backend: seed SQLite + vector store once, then run
python -m src.data.generate_customers   # also generate_transactions, generate_interactions, generate_support_tickets,
                                        # generate_fraud_alerts, generate_chat_transcripts, generate_complaints
python -m src.data.etl_pipeline
python -m src.rag.document_loader
uvicorn src.api.main:app --reload --port 8001      # docs at http://localhost:8001/docs

# Frontend (dev server on :3000, proxies the API to :8001)
cd frontend-react && npm install && npm run dev
npm run build                                       # tsc -b && vite build

# Tests (pytest.ini_options: pythonpath ".", "scripts/aml"; testpaths "tests")
pytest tests/                                       # everything
pytest tests/aml_copilot -q                         # AML copilot: all fakes, no credentials or network
pytest tests/lake -q                                # lakehouse + ML: local Spark, needs Java 17 (skips without it)
pytest tests/lake/test_ml_features.py::test_owner_features   # a single test

# Lint (CI lints the AML code only)
ruff check aml_copilot tests/aml_copilot scripts/aml
```

The top-level `tests/*.py` (TrustNova backend) need the seeded `banking.db` and the Chroma store; `tests/conftest.py` sets `DATABASE_URL`, `EMBEDDING_BACKEND`, `VECTOR_DB` before imports.

### Databricks (Free Edition workspace, CLI profile `trustnova`)

Two separate bundles:
- `databricks/lakehouse/databricks.yml` — lakehouse and ML jobs. Targets `staging` (catalog `trustnova_staging`, simulations HIS,LIS, negative ratio 50) and `prod` (catalog `trustnova_prod`, all six simulations, ratio 10). Jobs: `lakehouse`, `ml_train` (features → train), `ml_promote` (`model=m1|m3`), `ml_score`.
- `databricks.yml` at the repo root — the AML copilot jobs/pipeline (`aml-investigate`, `aml-canary`, reporting).

```bash
cd databricks/lakehouse
databricks bundle deploy -t staging -p trustnova
databricks bundle run ml_train -t staging -p trustnova
databricks auth login --profile trustnova           # when a call fails with "refresh token is invalid"
```

Production ML training takes ~3.3 h (features ~1 h, training + one-pass evaluation ~2 h); run it in the background. Serverless compute has no caching, a daily quota and no GPUs.

## Architecture notes that span files

**ML detection (`trustnova_ml`)** — the part under most active development.
- `features.py`: every feature is point-in-time — a transaction sees only activity strictly before its own minute (earlier minutes today + whole earlier days, windows of 1/7/28 days, per side with `s_`/`r_` prefixes). `FEATURES` is the model's input list; `BANNED` (`is_laundering`, `attempt_id`, `pattern_type`, `variant`, `entity_id`, `entity_name`) must never become features — `variant` encodes each simulation's laundering rate. `assign_split` does a temporal 60/20/20 split per simulation. Intermediate results read more than once go through `transaction_features(..., materialize)`: the job writes them to scratch tables `<catalog>.ml.tmp_*` (serverless Spark can't cache), tests use `localCheckpoint()` — without it the plan gets big enough to run local Spark out of memory.
- `jobs.py`: Databricks entry points (`features_main`, `train_main`, `promote_main`, `score_main`); `databricks/lakehouse/jobs/*.py` are thin wrappers (they must not `sys.exit(0)`, which Databricks reports as failure). Evaluation is one grouped pass over scored rows (`evaluate` → `report_from_counts`) because each extra pass rescores ~90M rows. Metrics come from binned counts (`metrics.BINS = 10000`), not row-level arrays.
- `train.py`: LightGBM training on all laundering rows + a hash-deterministic negative sample, isotonic calibration fitted on validation bins (logged as `calibration.json`), SHAP-style `top_reasons`, and `gate()`: a model must beat the rule baseline (`baseline.py`) on PR-AUC and recall@top-0.5%, overall and per simulation, to get the `@candidate` alias.
- Models score and explain using `booster.feature_name()`, not the current `FEATURES`, so an older champion keeps working after the feature set grows.
- Unity Catalog registry: `<catalog>.ml.m1_transaction_risk`, `<catalog>.ml.m3_pattern_type`. Moving `@candidate` → `@champion` (via `ml_promote`) requires the user's explicit approval for each version.
- Ground truth lives in `<catalog>.restricted.aml_labels` / `aml_patterns`; only training/evaluation read them.

**Lakehouse (`trustnova_lake`)**: account ids are namespaced `{variant}:{bank}:{account}` so the six IBM simulations never collide; the combined "bank" is six disconnected graphs. Transforms are pure DataFrame-in/DataFrame-out and tested on a local Spark sample (`tests/lake/sample_data.py`); a table whose columns changed is recreated only when every simulation is rewritten.

**AML copilot (`aml_copilot`)**: GenAI explains and documents alerts; it never raises or clears one. Its settings use `AML_`-prefixed env vars (`AML_LLM_PROVIDER`, `AML_LLM_MODEL`, ...) to avoid clashing with TrustNova's `LLM_PROVIDER`/`LLM_MODEL`; don't call its global `configure_logging()` from the host app. Not yet wired into the TrustNova API/UI.

**TrustNova backend (`src`)**: `src/api/main.py` mounts the route modules in `src/api/routes/`; auth/RBAC is `src/api/auth.py`. Note `require_permission` matches on the resource prefix (so `aml:read` satisfies `aml:sar`) — the integration plan adds an exact-match check for AML endpoints. Chat uses `src/api/llm_router.py` (Groq default) over the RAG stack in `src/rag/`.

## Repo rules

- Every change is committed and pushed to `main` on GitHub; a task isn't finished until the push succeeds. Don't commit the untracked local files (`.claude/`, `test_output.txt`, `tests/debug_fuzzy.py`, `tests/test_difflib_live.py`), `.env`, `banking.db`/`mlflow.db` or logs.
- Secrets (Groq key, `JWT_SECRET_KEY`, Databricks/GCP credentials) live only in `.env`; gitleaks runs in CI.
- Raw IBM dataset files never go into git (CDLA-Sharing-1.0; credit the source).
