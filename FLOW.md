# FLOW.md

How TrustNova works from start to finish: which file does what, in which order, and why. Four flows are **built
today**: a chat question, the data pipeline, model training and scoring, and an AML investigation. The last section
shows how they **will** connect (planned, not built yet).

```
                       ┌──────────────────────── built today ────────────────────────┐
 Browser (React)  ──►  FastAPI backend (src/)  ──►  SQLite banking.db + Chroma vectors
   frontend-react/       auth → route → RAG → agent → LLM (Groq) → trust score

 IBM AML files  ──►  Databricks lakehouse (trustnova_lake/)  ──►  ML (trustnova_ml/)
                      bronze → silver → gold                       features → train → gate → score → alerts

 One account id  ──►  AML Copilot (aml_copilot/)  ──►  SAR draft for a human
                      evidence → typology → narrative → faithfulness → conclude
                       └──────────────────────────────────────────────────────────────┘
```

---

## Flow A — a user asks the AI Copilot a question (built)

"Walk me through one request." The user types *"What are this customer's risk flags?"* in the chat screen.

| # | Where | What happens | Why |
|---|---|---|---|
| 1 | `frontend-react/src/features/chat/` → `services/api.ts` | The UI sends `POST /chat` with the question, an optional `customer_id` and the user's JWT token | One API call per question |
| 2 | `src/api/main.py` | FastAPI routes `/chat` to `src/api/routes/chat.py`. Security headers and CORS are applied to every response | The app's front door |
| 3 | `src/api/auth.py` (`get_current_user`, `require_permission("chat:all")`) | Decodes the JWT (logged in earlier through `POST /auth/login`), loads the user's role and permissions (13 roles), rejects the user if they lack `chat` | Role-based access control |
| 4 | `chat.py` guards | Blocks jailbreak attempts and "write actions" ("transfer $500...") with a fixed reply, and writes an audit entry | Chat may only read, never act |
| 5 | `src/rag/entity_memory.py`, `query_rewriter.py`, `src/api/memory.py` | Resolves which customer "his" or "the account" means from the session, and rewrites vague questions into complete ones. If it still can't tell, it asks the user to pick a customer | Follow-up questions work across turns |
| 6 | `src/rag/query_router.py` (+ `semantic_router.py`) | Builds a **retrieval manifest**: which sources to ask (SQL tables, risk engine, fraud engine, policy documents), filtered by the user's permissions (`rbac_filter.py`) | Fetch only what the question and the role need |
| 7 | `src/rag/parallel_retriever.py` → `data_retriever.py`, `hybrid_retriever.py` | Queries every source **at the same time** (`asyncio.gather`): SQL facts from `banking.db`, risk and fraud scores, and policy chunks from **hybrid search** (BM25 keyword search plus Chroma vector search) | Faster, and answers combine data and policy |
| 8 | `src/rag/context_fusion.py` | Merges the results into one labelled context block (database facts first, documents last) | The LLM sees the most reliable facts first |
| 9 | `src/agents/registry.py` → `base_agent.py` → `src/api/llm_router.py` | Picks the agent for the user's role (Customer 360, AML, KYC, Fraud, Risk, Loan, Policy, Compliance, Treasury, Executive), builds its prompt and calls the LLM (Groq, with OpenAI as fallback) | Role-specific instructions |
| 10 | `src/rag/verification.py` | Checks every number in the answer against the retrieved SQL and document text, and records any mismatch | Catches made-up figures |
| 11 | `src/models/ai_trust.py`, `trust_scorer_v2.py` | Scores the answer (0–100) on retrieval confidence, hallucination risk, citation quality and more | The user sees how far to trust the answer |
| 12 | `chat.py` → `auth.log_audit` | Saves memory for the next turn, writes the audit log and returns the answer, sources and trust score | Traceability |
| 13 | `frontend-react/src/features/chat/` | Shows the answer with a collapsible trust badge | — |

**Where is the RAG?** `src/rag/`: routing (`query_router.py`), retrieval (`parallel_retriever.py`, `hybrid_retriever.py`, `vector_store.py`, `embeddings.py`), fusion (`context_fusion.py`) and checking (`verification.py`). Documents are indexed by `src/rag/document_loader.py` from `data/raw/banking_docs/`.

**Where are the agents?** There are two kinds:
- **Chat agents** in `src/agents/registry.py`: one class per banking role, all built on `base_agent.py`.
- **The AML investigation agents** in `aml_copilot/agents/` (Flow D): a LangGraph pipeline, not a chat agent.

---

## Flow B — raw IBM files become clean tables (built, Databricks)

Job `lakehouse` in `databricks/lakehouse/databricks.yml`. Every task file in `databricks/lakehouse/jobs/` is a thin wrapper around `trustnova_lake/jobs.py`.

| # | Task | Reads → writes | What it does |
|---|---|---|---|
| 1 | bronze | CSV files in volume `raw.ibm_aml` → `bronze.*` | Copies the raw rows as they are, adding the simulation (`variant`) and the file name |
| 2 | silver | `bronze.*` → `silver.transactions`, `silver.accounts`, `silver.fx_rates`, `restricted.aml_labels`, `restricted.aml_patterns` | Types every column, builds the ids (`{variant}:{bank}:{account}`), converts amounts to USD with rates measured from the data, and moves labels into a locked schema |
| 3 | gold | `silver.*` → `gold.account_txn_edges`, `gold.account_summary` | Two rows per payment (one per account side), so one lookup returns an account's money in and out |
| 4 | quality | all of the above | 26 checks (row counts against the files, every pattern line matched, no null ids...). If any fails, the load doesn't count |

The logic lives in `trustnova_lake/transforms.py` (Spark, DataFrame in → DataFrame out). It is tested on a small fake bank in the exact IBM formats (`tests/lake/sample_data.py`).

---

## Flow C — train, check, approve and score a model (built, Databricks)

Code: `trustnova_ml/`. Jobs: `ml_train`, `ml_promote`, `ml_score`.

```
gold + silver tables
   │  features_main        trustnova_ml/features.py: 177 point-in-time features per transaction
   ▼                       (amounts, account history, owner history, cycles, pass-through chains)
ml.txn_features  (+ split: train 60% / valid 20% / test 20%, by time, per simulation)
   │  train_main           trustnova_ml/jobs.py + train.py
   ▼   1. join the locked labels (training only)
       2. all laundering rows + a sample of normal rows → LightGBM M1 (risk) and M3 (pattern type)
       3. score valid + test once → counts per score bucket → precision / recall / PR-AUC
       4. calibrate the scores (isotonic regression on validation)
       5. gate: beat the rule baseline (baseline.py) overall and in every simulation?
          yes → register in Unity Catalog as @candidate (MLflow)
   │  ml_promote           a person approves: @candidate → @champion
   ▼
   │  ml_score             score new transactions with @champion, roll up per account per day,
   ▼                       keep the top accounts within the alert budget (25 per simulation per day),
ml.txn_scores, ml.account_day_scores, ml.ml_alerts   (score, top reasons, model version, M3 pattern)
```

- **Why "point-in-time":** in production you only know the past. Every feature uses activity strictly before the payment's own minute, and tests check that removing later data changes nothing.
- **Why a gate and a person:** a model can look good on average and still fail on one simulation; the gate checks each one, and a human signs off.
- **Status:** the first production scoring run (24 Nov 2026, champion v3, 108 minutes) wrote 9,822 alerts. See `docs/AML_INTEGRATION_PLAN.md` for what they contain.

---

## Flow D — the AML Copilot investigates one account (built, runs on Databricks; not in the UI yet)

Entry points: `aml_copilot/dbx/investigate.py` (`investigate(...)`: daily quota, no duplicate runs, hash-chained audit log) → `aml_copilot/agents/investigation.py` (`run_investigation`), a **LangGraph** graph:

```
evidence ──► typology ──► narrative ──► faithfulness ──► conclude
   │             │             │                            ▲
   └── error ────┴── error ────┴────────────────────────────┘
```

| Step | File | What it does |
|---|---|---|
| evidence | `agents/evidence.py`, `ingestion/` | Pulls the account's transactions, profile and case history, then follows the money to linked accounts (up to 4 hops / 30 accounts / 500 rows). Rule scores come from `detection/` (to be replaced by the ML score) |
| typology | `agents/typology.py`, `retrieval/` | Retrieves typology documents (`data/typology_docs/`) and has the LLM judge which match. Code removes any match citing a document that wasn't retrieved |
| narrative | `agents/narrative.py` | Drafts the SAR narrative. Code removes any sentence with an amount, date or id that isn't in the evidence |
| faithfulness | `guardrails/faithfulness.py` | A second LLM must quote evidence for every sentence |
| conclude | `investigation.py` (`decide_outcome`) | Ends in `draft_ready` (needs a human), `no_action`, `incomplete` (a source was down, which is never treated as "all clear") or `failed` |

A person always makes the final decision (`databricks/notebooks/review.py`).

---

## How they will connect (planned — see `docs/AML_INTEGRATION_PLAN.md`, Phases 3–9)

```
ml.ml_alerts ──nightly sync──► Supabase aml_alerts → aml_cases ──► AML Center screen
                                                                     │ "Run AI Investigation"
                                                                     ▼
                         POST /aml/investigations ──► Cloud Tasks ──► Flow D (with the ML score
                                                                     and reasons as evidence)
                                                                     ▼
                                       SAR draft + trust score ──► analyst approves / rejects / escalates
```

Not built yet: Supabase, the `/aml/investigations` routes, the AML Center button, Vertex Vector Search and the GCP deployment.
