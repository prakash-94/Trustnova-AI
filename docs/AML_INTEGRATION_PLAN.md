# TrustNova AI + AML Copilot: Merge and Integration Plan

**Status:** Plan only. Nothing here has been built yet.
**Deliverable once approved:** save this document as `docs/AML_INTEGRATION_PLAN.md` in the TrustNova AI repo, then commit and push it (per the project's GitHub sync rule). No code changes are part of that step.

## Decisions taken
| Topic | Decision |
|---|---|
| Codebase | **Merge** AML Copilot into the TrustNova AI repo as one product. It runs inside the same backend process. |
| Data | The **entire IBM AML dataset**: all six files loaded as **one combined bank**, about 9.5M accounts and 430M transactions. |
| Transactions | **Databricks on GCP** (Delta tables in Unity Catalog). |
| Customers and all app data | **Supabase** (Postgres). Salesforce is retired because it can't hold millions of customers. Cloud SQL and SQLite are retired too. |
| Vector search | **Vertex AI Vector Search**, a dedicated, separately scalable GCP service, with Vertex AI embeddings. |
| AML detection | **Trained machine-learning models** decide what is suspicious. The champion is a **LightGBM** model on transaction and graph features; the challenger is a **graph neural network (Multi-GNN)**. They are trained, registered and served on Databricks (MLflow). GenAI doesn't do detection. |
| GenAI | **Agents only:** the evidence summary, the typology explanation, the SAR narrative, the faithfulness check and chat. The agents explain and document the model's alerts. They never raise or clear an alert themselves. |
| Production | **GCP**: Cloud Run, Cloud Tasks, Vertex AI, Secret Manager and Firebase Hosting. This replaces Render and Vercel. |

---

## 1. Context

### What TrustNova AI has today
- **AML is read-only and shows the wrong data.** The three GET endpoints in `src/api/routes/aml.py` read `fraud_alerts` and label them as AML cases. The real `aml_cases` table (80 rows) is only counted in `src/api/routes/kpi.py`. `sar_filed` is hard-coded to `False`.
- **The AML chat agent has no tools.** `AMLAgent` in `src/agents/registry.py` is just a prompt.
- **The investigation narrative is a template.** `AMLCenter.tsx` builds it client-side with `generateInvestigationNarrative`; no LLM is involved.
- **Two permission problems.** `aml:write` and `aml:sar` are granted to roles but never checked. `require_permission` matches on the prefix, so `aml:read` would satisfy `aml:sar`.
- **Small data.** About 1,000 synthetic customers and 15K transactions in SQLite, plus five in-memory `CX-10000x` mock customers.

### What AML Copilot (`E:\AML`) provides
For one account, a LangGraph pipeline runs **Evidence → Typology (RAG) → SAR Narrative → Faithfulness check → Conclude**:
- **Evidence:** pulls the account's transactions, profile and case history, then expands to linked accounts (up to 4 hops / 30 accounts / 500 rows).
- **Risk score:** rule-based. Structuring and layering each add +50.
- **Typology matching:** an LLM judges the retrieved typology docs. Code removes any match that cites documents that weren't retrieved.
- **SAR narrative:** code removes any sentence with an amount, date or id that isn't in the evidence.
- **Faithfulness:** a second LLM must quote evidence for every sentence.

Every run ends in one of four outcomes: `draft_ready`, `no_action`, `incomplete` or `failed`. Its evaluation scores 100% on tier and typology, with 97–99% of sentences supported.

**Pieces to reuse:**
- `run_investigation(...)` and `to_api_result(state)`.
- `dbx/investigate.py::investigate(...)`: daily quota, duplicate-run prevention, hash-chained audit, with the store, audit, run function and clock passed in.
- The `DocumentBackend` and `ObjectBackend` protocols.
- `DatabricksSource`.
- Supabase `case_history` access, which already exists.

### The IBM dataset (CDLA-Sharing-1.0)
The dataset is six simulations: HI and LI (higher / lower laundering share) × Small, Medium and Large.
- **Size:** 41.6 GB in total, 12 files (a `*_Trans.csv` and a `*_Patterns.txt` for each simulation).
- **Transaction columns:** `Timestamp, From Bank, Account, To Bank, Account.1, Amount Received, Receiving Currency, Amount Paid, Payment Currency, Payment Format, Is Laundering`.
- **Laundering patterns:** the patterns files label attempts as fan-out, fan-in, cycle, gather-scatter, scatter-gather, stack, bipartite or random.
- **Why it fits:** both sides of every transfer are recorded, which AML Copilot needs to follow money between accounts and detect layering.
- **What it lacks:** customer profiles, KYC, PEP status, merchants, locations, devices and sentiment.

**Known effects of combining all six into one bank** (accepted, and documented in the UI and README):
- The six files never pay each other, so the bank is six unconnected groups of accounts and money-tracing never crosses between them.
- All six cover overlapping dates (Aug–Nov 2022).
- The overall laundering rate is a blend of HI and LI. Every row keeps a `variant` column so metrics can still be reported per file.

### Intended outcome
TrustNova and AML Copilot become one app on one bank: about 9.5M customers in Supabase, 430M transactions in Databricks, and one shared document search on Vertex AI. A trained ML model scores every transaction and account, and the highest-risk accounts become cases. An AML analyst picks a case and clicks **Run AI Investigation**. They get:
- the ML risk score with its top reasons (SHAP)
- cited typology matches
- a SAR draft with each sentence marked supported or unsupported
- investigator questions

They can then approve, reject or escalate it. Every step is audited.

---

## 2. Target architecture

```
Firebase Hosting (React)  ──/api/**──►  Cloud Run: trustnova-api (merged backend, one process)
                                          ├─ /customers, /transactions, /kpi ...  (repository layer)
                                          ├─ /aml/cases            (rewritten → Supabase aml_cases)
                                          ├─ /aml/investigations   (NEW)  ──enqueue──► Cloud Tasks
                                          ├─ /internal/aml/run/{id} (NEW, OIDC-only) ◄──┘
                                          │     └─ aml_copilot.investigate(...)  (merged package)
                                          ├─ /chat (Groq)  + AI Trust Score
                                          │
              ┌───────────────────────────┼───────────────────────────────┐
              ▼                           ▼                               ▼
   Supabase Postgres              Databricks on GCP                Vertex AI
   customers (~9.5M), KYC,        Unity Catalog (GCS):             Vector Search index
   users, aml_cases, alerts,      bronze → silver → gold           (banking_docs + typology_docs)
   investigations, audit,         account_txn_edges (430M×2)       text embeddings
   rag_chunks, account_summary    aml_labels (restricted)          Claude models (GenAI agents only)
                                  ML: feature tables → MLflow
                                  → UC Model Registry → batch scoring
                                  + Model Serving endpoint
              ▲                           │
              └──── nightly sync job ─────┘  (account summaries + ML alerts with reason codes)
```

**Who does what:**
- **ML models (Databricks)** decide risk: transaction scores, account scores and the predicted laundering pattern.
- **GenAI agents (Claude on Vertex)** investigate and explain those alerts and draft the SAR, but never change a score.
- **Chat (Groq)** answers analysts' questions.

**Local development** uses the same code with:
- the Supabase CLI's local Postgres in Docker
- a Databricks dev catalog with a small sampled slice
- Chroma (`VECTOR_BACKEND=chroma`) instead of Vector Search

Postgres runs in every environment, so there are no SQLite/Postgres SQL differences to manage.

---

## 3. Work plan

### Phase 0 — Prerequisites
1. **Accounts and services.**
   - Create GCP projects `trustnova-staging` and `trustnova-prod`.
   - Enable these APIs: Run, Cloud Tasks, Vertex AI, Secret Manager, Artifact Registry, Cloud Storage, Firebase.
   - Request access to the Claude models in Vertex AI Model Garden.
2. **Databricks on GCP.** Create a workspace from the GCP Marketplace with a Unity Catalog metastore on a GCS bucket. Create catalogs `trustnova_dev`, `trustnova_staging` and `trustnova_prod`, and a serverless SQL warehouse for each environment.
3. **Supabase.**
   - Create a Pro project for production (plus one for staging), in the AWS region closest to the GCP region (for example `us-east-1` ↔ GCP `us-east4`).
   - Size it for about 9.5M customers plus indexes, around 20–30 GB with a larger compute add-on.
   - Allow connections only from the Cloud Run egress IP (fixed through Cloud NAT) and the Databricks egress range.
4. **Dataset.** The user downloads all 12 files from Kaggle with their own login, then uploads them to `gs://trustnova-prod-raw/ibm_aml/` with `gcloud storage cp` (resumable). Raw files never go into git.

### Phase 1 — Merge the repositories
1. **Bring in AML Copilot with its history.** Run `git subtree add --prefix=_aml_import <AML repo> main` in the TrustNova repo. In the next commit, reorganise with `git mv`:

   | From (AML repo) | To (merged repo) |
   |---|---|
   | `aml_copilot/` | `aml_copilot/` at the repo root, so its imports don't change |
   | `tests/` | `tests/aml_copilot/` |
   | `typology_docs/` | `data/typology_docs/` |
   | `databricks/` and `databricks.yml` | `databricks/` (job bundle only) |
   | `docs/` | `docs/aml/` |
   | `evaluation_results/`, `sample_runs/` | `docs/aml/` |

   Adopt AML's `.gitleaks.toml` for the whole repo and merge its GitHub workflows. Archive the old AML GitHub repo as read-only, with a README pointing to the merged repo.
2. **Retire what is no longer needed:**
   - the Databricks App web app (`dbx/webapp.py`, `dbx/appmain.py`), since TrustNova's UI replaces it
   - the Delta job store (`service/delta.py`), since Supabase replaces it
   - the Salesforce source and seed scripts (`generate_salesforce_customers.py`, `customer_profiles*.csv`)
   - the stale `build/` and `dist/` folders
3. **Separate the environment variables.** Both apps use `LLM_PROVIDER` and `LLM_MODEL` with different meanings. Rename AML's settings to `AML_LLM_PROVIDER`, `AML_LLM_MODEL`, `AML_TYPOLOGY_MODEL`, `AML_NARRATIVE_MODEL` and `AML_FAITHFULNESS_MODEL` in `aml_copilot/config.py`. The host app builds `Settings(_env_file=None, ...)` explicitly.
4. **One Python and one set of dependencies.**
   - Standardise on Python 3.12 and one `requirements.txt`.
   - Raise TrustNova's `fastapi<0.137` cap; the AML web app that needed fastapi ≥ 0.141 is gone. Upgrade `langchain` to ≥ 1.4.
   - Add `langgraph`, `pydantic-settings`, `structlog`, `tenacity`, `pypdf`, `databricks-sql-connector`, `psycopg[binary]`, `google-cloud-aiplatform`, `google-cloud-tasks` and the Vertex Claude client.
   - Move `torch`, `sentence-transformers` and `chromadb` to an optional `requirements-local.txt`, since production embeddings come from Vertex.
5. **Logging.** Never call AML Copilot's global `configure_logging()` from the host app. Use TrustNova's logging setup instead, as JSON to stdout.
6. **Gate:** both test suites (TrustNova `tests/` and `tests/aml_copilot/`) pass in the merged repo before anything else changes.

### Phase 2 — Transaction data platform (Databricks on GCP)
These are Databricks Jobs in the merged `databricks/` bundle, deployed with `databricks bundle deploy -t <env>`.

1. **Bronze.** Auto Loader reads all 12 files from GCS into `bronze.ibm_transactions` and `bronze.ibm_patterns`, adding `variant` (`HIS`, `HIM`, `HIL`, `LIS`, `LIM` or `LIL`) and the source file name.
2. **Silver.**
   - **`silver.transactions`:** one typed row per transaction.
     - `txn_id`, built as `{variant}-{row_number}`
     - `timestamp`
     - `from_account` / `to_account`, namespaced as `{variant}:{bank}:{account}` so overlapping numbers never collide
     - `amount_paid`, `paid_currency`, `amount_received`, `received_currency`
     - `amount_usd`, converted with a fixed FX table stored in `silver.fx_rates` and documented
     - `payment_format`
     - `variant`
   - **`silver.aml_labels`:** `txn_id` and `is_laundering`. This table is **restricted in Unity Catalog** to the evaluation service principal. The API and copilot principals can't read it.
   - **`silver.aml_patterns`:** `attempt_id`, `pattern_type`, `txn_id`, `variant`. Also restricted, because it is ground truth.
3. **Gold.**
   - **`gold.account_txn_edges`:** one row per (account, transaction, direction), about 860M rows, with liquid clustering on `account_id` and `timestamp`. One clustered lookup returns all money in and out of an account. This is what AML link expansion and TrustNova's transaction views query.
   - **`gold.account_summary`:** per-account counts, totals, distinct counterparties, first and last activity, payment-format mix, and daily balances proxy.
   - **Feature tables for the ML models (Phase 2B).** These are Unity Catalog feature tables, computed **point-in-time**: each transaction's features use only activity up to its own timestamp.
4. **Nightly sync job.** Pushes `gold.account_summary` and new ML alerts (`gold.ml_alerts`, Phase 2B) into Supabase (`account_summary` and `aml_alerts`). Supabase therefore holds what screens need instantly, and Databricks holds the bulk.
5. **Cost controls.** Run the one-time backfill on a job cluster sized for it, then switch to incremental runs. The SQL warehouse auto-stops after 10 minutes idle.

### Phase 2B — ML detection: training and production scoring (Databricks)
GenAI isn't used anywhere in this phase. Everything runs as Databricks Jobs in the `databricks/` bundle, tracked in MLflow, with models registered in the Unity Catalog Model Registry.

**1. Prediction targets.**

| Model | Granularity | Label (from restricted `silver.aml_labels` / `aml_patterns`) | Purpose |
|---|---|---|---|
| **M1 Transaction risk** | per transaction | `is_laundering` | the core detector |
| **M2 Account risk** | per account per day | 1 if any of the account's transactions in the window is laundering | turns transaction scores into account alerts and cases |
| **M3 Pattern classifier** | per flagged account | pattern type: fan-out, fan-in, cycle, gather-scatter, scatter-gather, stack, bipartite, random or "other" | predicts the likely typology to hand to the GenAI typology agent |

**2. Features.** These come only from transaction behaviour, computed point-in-time in Spark.
- **Transaction:** `amount_usd`, currency and payment format, cross-currency and cross-bank flags, hour and weekday.
- **Account windows** (1 h / 24 h / 7 d / 30 d): count, sum, mean and standard deviation of amounts, distinct counterparties in and out, new-counterparty rate, cash and wire share, and structuring-band counts ($7k–$10k in USD).
- **Graph:**
  - fan-in and fan-out degree per window
  - scatter-gather and gather-scatter motif counts
  - short-cycle participation (4 hops or fewer within 7 days), using GraphFrames and Spark SQL; IBM's Graph Feature Preprocessor (Snap ML) is an option to evaluate
  - 2-hop counterparty risk, computed from earlier scores only, to avoid leakage
- **Never used as features:**
  - `is_laundering`, pattern ids or `variant` (it encodes the HI/LI laundering rate)
  - the synthetic customer profile fields (name, age, income, PEP and so on), which are random and would only add noise and potential bias

  The former rule detectors (structuring, fan-in/out, cycles, gather-scatter) become **features and reason codes** instead of points-based scores.

**3. Models.**
- **Champion: LightGBM** gradient-boosted trees for M1, M2 and M3.
  - It is strong on tabular plus graph features, which is in line with the IBM dataset's published benchmarks.
  - It trains quickly on Spark, using distributed LightGBM (SynapseML) or `xgboost.spark` as a fallback.
  - Scoring is cheap and needs only a CPU.
  - **SHAP** explanations give per-alert reason codes, which the SAR narrative and model validation both need.
- **Challenger: Multi-GNN.** This is IBM's open-source PNA-based graph neural network for directed multigraphs, with edge updates, reverse message passing, ego IDs and port numbering. It is trained for M1 on Databricks GPU job clusters.
  - It is promoted only if it beats the champion on the held-out test set (minority-class F1 and recall at the alert budget) **and** its alerts can be explained well enough (GNNExplainer reason codes reviewed by a person).
  - Until then it runs in shadow mode: scored and logged, never alerting.
- **Baseline:** the rule-only detector, kept to prove each model adds value.

**4. Training setup.**
- **Temporal split per variant.** For each of the six variants, order transactions by time and split 60 / 20 / 20 into train, validation and test. The variants cover different date ranges, so each is split on its own timeline. Test windows are never used for tuning.
- **Class imbalance** (about 1 laundering transaction in 800–1,950):
  - Keep every positive, down-sample negatives about 50:1 for training only, and correct the scores afterwards with isotonic calibration on the untouched validation set.
  - Tune `scale_pos_weight` and the other settings with Optuna on the Spark cluster.
- **Metrics:** minority-class F1 (the dataset's standard metric), PR-AUC, recall at the alert budget, and precision of generated alerts. Each is reported overall, **per variant** and **per pattern type**.
- **Alert threshold.** Set by **alert budget**: the number of new cases per day the analyst team can work, recorded as a config value, not as a fixed score cutoff.

**5. Production scoring.**
- **Batch.** An hourly or nightly job scores new transactions with M1, rolls them up with M2 to `gold.ml_scores`, keeps accounts above the budget threshold in `gold.ml_alerts` (score, top 5 SHAP reasons, cited `txn_id`s, model version), runs M3 on those accounts, and syncs everything to Supabase `aml_alerts` → `aml_cases`.
- **Online.** A **Databricks Model Serving** endpoint (serverless, scales to zero off-peak) serves M2 and M3 so the copilot can re-score an account on demand when an analyst opens an investigation. Features are looked up from the online feature table.
- **Every score records its `model_name@version`**, so any case can be traced to the exact model that raised it.

**6. Governance and monitoring** (in the style of SR 11-7 model risk management).
- **Documentation:** a model card and validation report for each registered version, covering data, features, metrics per variant and pattern, limitations and the known effects of combining all six files into one bank.
- **Promotion:** UC Model Registry aliases `@champion` and `@challenger`. Promotion needs the evaluation gate plus a manual approval.
- **Monitoring:** Databricks Lakehouse Monitoring on feature drift, score distribution, daily alert volume and analyst outcomes. Approve, reject and escalate decisions flow back from Supabase into a monitoring table.
- **Retraining:** monthly, or when drift alerts fire. A retrain goes through the same evaluation gate.

### Phase 3 — Customers and app data in Supabase
1. **Schema.** Use Supabase CLI migrations in `supabase/migrations/*.sql`, which replace the ad-hoc `run_migrations()` and `ensure_indexes()`.
   - **`customers`:**
     - `customer_id`, `name`, `email`, `phone`, `dob` / age
     - `customer_type` (individual or business), `occupation` / industry
     - `annual_income`, `credit_score`, `segment`
     - `aml_risk_rating`, `is_pep`, `is_sanctioned`
     - `kyc_status`, `kyc_last_reviewed`
     - address fields, `created_at`
   - **`customer_accounts`:** `customer_id`, `account_id`, `bank_id`, `variant`.
   - **Indexes:** a `pg_trgm` index on name (fuzzy search over 9.5M rows) and B-tree indexes on email, risk rating and KYC status.
2. **Customers from accounts.** If the download includes an account-to-entity mapping file, group accounts into customers with it. Otherwise create **one customer per account** (about 9.5M). Accounts are never grouped arbitrarily, because that would invent links between accounts and mislead link analysis.
3. **Synthetic profiles at scale.**
   - Generate them in Databricks with a pandas UDF and Faker, seeded by a hash of `account_id`, so every profile can be reproduced with no stored state.
   - `customer_type` comes from observable activity, such as volume and counterparty count.
   - **No profile field may be derived from laundering labels or patterns.** `aml_risk_rating` comes from the synthetic attributes and observable activity only. A test enforces this.
   - Bulk-load with Postgres `COPY` over Supabase's direct connection (port 5432, not the pooler), in batches of 500K or fewer.
4. **Move the remaining TrustNova tables to Supabase:** `users`, `audit_log`, `kyc_records`, `aml_cases`, `aml_alerts`, `access_requests`, `notifications`, `announcements`, `trust_scores`, `ai_trust_scores`, `feedback`, `ai_feedback`, `llm_usage`, `sessions`, `credit_card_applications` and `loans`, plus the new `aml_investigations`, `aml_investigation_audit`, `rag_chunks` and `account_summary`.
   - Demo users and roles are re-seeded.
   - Old synthetic data tied to the 1,000 legacy customers is dropped: transactions, sentiment, interactions, complaints, chat transcripts and support tickets. Interactions, complaints and sentiment are regenerated for a seeded sample of about 50K new customers, so those screens still have data. For everyone else they show "not available".
5. **Case queue.** `aml_cases` is filled from `aml_alerts` (ML model output with score, reason codes, predicted pattern and model version) and assigned to analysts. Ground truth is **not** used to create cases; it is used only to measure how many real laundering attempts the ML alerts catch.
6. **Access.**
   - The backend connects with a dedicated least-privilege Postgres role, not the `service_role` key.
   - Row Level Security is enabled with deny-all for the `anon` and `authenticated` roles.
   - Supabase keys never reach the frontend.
   - TrustNova keeps its own JWT login.
7. **Golden fixtures.** The loader writes a documented list of about 20 fixed customers, covering each pattern type, PEP, KYC-pending and clean customers, to `tests/fixtures/golden_customers.json`. These replace the `CX-10000x` mocks in all tests.

### Phase 4 — Retrieval on Vertex AI Vector Search
1. **One index.** Create one Vector Search index with streaming updates enabled, deployed to a dedicated index endpoint that autoscales its replicas. Each vector carries two filter tags:
   - `collection`: `banking_docs` or `typology_docs`
   - `doc_type`: used for TrustNova's role-based document filtering through `rbac_filter.get_doc_type_filter`
2. **Embeddings** come from a Vertex AI text-embedding model. Chunk text and metadata live in Supabase `rag_chunks`; Vector Search stores only the id, vector and filter tags. The retriever fetches the text by id.
3. **Indexing job.** A Cloud Run Job chunks `data/raw/banking_docs/` and `data/typology_docs/`, embeds the chunks, writes them to `rag_chunks` and upserts them into Vector Search. It runs whenever docs change (a CI step when anything under `data/**/docs` changes).
4. **One retrieval layer.** `src/rag/vector_store.py` gets a backend interface with two implementations: `vertex` (production) and `chroma` (local). AML's `retrieval/store.py` is rewritten to call it with `collection=typology_docs`. BM25 keyword search in `src/rag/hybrid_retriever.py` keeps working on the in-memory chunk list loaded from `rag_chunks`.
5. **Re-check quality.** The embedding model changes from MiniLM, so re-run AML Copilot's evaluation and TrustNova's RAG tests. The pass bar is typology precision and recall no worse than today, and at least 95% of SAR sentences supported.

### Phase 5 — AML Copilot changes (inside the merged repo)
1. **Account IDs.** `aml_copilot/ids.py` gets a configurable pattern, `AML_ACCOUNT_ID_PATTERN`, defaulting to `^(HIS|HIM|HIL|LIS|LIM|LIL):[0-9]+:[0-9A-F]+$`. `StartRequest` and the narrative id checks use the same validator.
2. **Data sources.**
   - Transactions: `DatabricksSource` queries `gold.account_txn_edges` (the clustered lookup) with `TRANSACTION_ROW_LIMIT`. Labels are never selected, and the API principal can't read them anyway.
   - Customer profile: a new `SupabaseProfileSource` reads `customers` and `customer_accounts`, replacing `SalesforceSource`.
   - Case history: `case_history` moves to Supabase `aml_cases` and investigation history.
   - `run_investigation(...)` gains an optional `ingest_fn` parameter that passes through to `build_evidence_graph(ingest_fn=...)`.
3. **Job and audit storage.** New Supabase-backed implementations of `DocumentBackend` and `ObjectBackend` in `aml_copilot/service/supabase_store.py`, used by `investigate(...)`.
4. **Detection comes from the ML model.**
   - The evidence graph's `score` step in `agents/evidence.py` stops computing rule points. It reads the account's ML result instead: `gold.ml_scores`, or a fresh score from the Model Serving endpoint, with the account score, risk tier (from calibrated thresholds), top SHAP reason codes, predicted pattern (M3) and model version.
   - `detection/risk_score.py` becomes a thin client that returns this as `RiskScore`.
   - The rule functions move into the Phase 2B feature code. They also remain as the offline baseline.
   - If the ML score can't be fetched, the run ends `incomplete` with `missing_sources=["ml_score"]`. It never falls back silently to rules, following AML Copilot's rule that a missing source is never treated as all-clear.
5. **GenAI agents work on the model's output.**
   - The typology agent receives the M3 prediction and SHAP reasons as context, retrieves typology docs, and explains whether the evidence supports the predicted pattern. It reports when the evidence doesn't support it. It cannot change the score or tier.
   - The narrative agent cites the reason codes and transactions.
   - Faithfulness checking stays the same.
   - `should_draft` is triggered by the ML tier (medium or higher).
6. **Typology docs.** Add one doc to `data/typology_docs/` for each of the 8 IBM patterns, with red flags and investigator questions in the format `retrieval/questions.py` expects.
7. **Evaluation** (of the GenAI agent pipeline; ML model evaluation is in Phase 2B).
   - `evaluation/dataset.py` samples accounts from `silver.aml_patterns` (laundering) and clean accounts, through the evaluation principal, with expected tier and typology taken from the pattern.
   - Results are reported overall **and per variant**, because of the blended rate.
   - Cost stays capped with `BudgetMeter`.
   - It runs as a Databricks Job, plus a small canary in CI.
8. **LLM provider (agents only).**
   - The pipeline uses Claude on Vertex (`AML_LLM_PROVIDER=vertex`, `GCP_AUTH=adc`): `claude-haiku-4-5` for summaries and `claude-sonnet-5` for typology, narrative and faithfulness.
   - Local development can use the `anthropic` provider with a key in `.env`.
   - TrustNova chat stays on Groq.

### Phase 6 — TrustNova backend integration
1. **Repository layer, `src/data/repositories/`.**
   - `CustomerRepo` (Supabase): search with trigram matching and keyset pagination; the API never lists everything.
   - `TransactionRepo` (Databricks): recent transactions for an account or customer, at most 100 rows per call, with a short in-process cache.
   - `SummaryRepo` (Supabase `account_summary`).

   Repoint `/customers`, `/transactions`, `/kpi`, Customer 360 and the chat data retriever (`src/rag/data_retriever.py`) to these. Remove the in-memory `CX-10000x` mocks from the route files.
2. **AML routes.**
   - **`src/api/routes/aml.py`:** `/aml/cases` reads Supabase `aml_cases` joined to `customers` and `aml_alerts`. It returns 404 for unknown ids and applies filters before `LIMIT`.
   - **`src/api/routes/aml_investigations.py` (new):**

   | Method & path | Permission (exact match) | Behaviour |
   |---|---|---|
   | `POST /aml/investigations` `{case_id \| account_id}` | `aml:write` | 202 with `{job_id}`; 409 if a run is already in progress |
   | `GET /aml/investigations[?customer_id&status]` | `aml:read` | list jobs |
   | `GET /aml/investigations/{id}` | `aml:read` | status, current step, `InvestigationResult` |
   | `GET /aml/investigations/{id}/audit` | `aml:read` | hash-chained audit events |
   | `POST /aml/investigations/{id}/decision` `{decision, comment, result_hash}` | `aml:sar` | approve, reject or escalate; the hash must match; approving sets `aml_cases.sar_filed` |
   | `POST /internal/aml/run/{job_id}` | Cloud Tasks OIDC only | runs `investigate(...)` for the whole request |

3. **`src/api/auth.py`.**
   - Add `require_exact_permission`; admin `*` still passes. Use it on every endpoint in the table above.
   - `log_audit` writes to Supabase and stores `role` and `customer_id` (add those columns).
   - Remove the hard-coded `JWT_SECRET_KEY` fallback.
4. **`src/aml/dispatch.py`.** `AML_DISPATCH` selects how runs are started: `thread` (local, a single-worker pool) or `cloud_tasks` (staging and production).
5. **AI Trust Score.** When a narrative is produced, call `get_ai_trust_scorer().score(...)` with the narrative, the cited evidence and typology chunks, and `is_db_grounded=True`. Show it next to the faithfulness ratio. Both are reported honestly.

### Phase 7 — Frontend (`frontend-react/`)
1. **API client and types.** `services/api.ts` gets `amlApi.startInvestigation`, `investigation`, `investigations`, `audit` and `decide`, and the API base becomes the relative `/api`. `types/banking.ts` gets `Investigation` and `InvestigationResult`.
2. **AML Center (`features/aml/AMLCenter.tsx`).**
   - Remove `generateInvestigationNarrative`.
   - Add a **Run AI Investigation** button for users with `aml:write`.
   - Poll every 3 s and show which step the run is on.
   - The result view shows:
     - the risk breakdown
     - cited typology matches
     - the SAR draft with each sentence marked supported or unsupported
     - investigator questions
     - a prominent warning for `incomplete` runs
     - the AI Trust badge
     - a table of the counterparty accounts involved
   - An approve, reject or escalate bar appears only for users with `aml:sar`, with the audit trail below it.
3. **Large-data handling.** Customer search becomes server-side with debounced typing and paging. Transaction lists load lazily. A small "Synthetic data — IBM AML dataset (CDLA-Sharing-1.0)" note appears in the footer.

### Phase 8 — Chat
`AMLAgent` gets the latest investigation result for the customer in context, through `structured_context`, so analysts can ask questions about a SAR draft. Starting an investigation or filing a SAR stays UI-only, and the write-action guard in `chat.py` stays as it is.

### Phase 9 — GCP production and cut-over
See §5 for the environment. The order is:
1. Terraform for staging.
2. Databricks bundle deploy and backfill.
3. Supabase migrations and bulk load.
4. Vector indexing job.
5. ML backfill: compute features, train, run the evaluation gate, register `@champion`, run batch scoring.
6. Deploy and smoke test (§7, item 8).
7. Repeat for production.
8. Switch DNS to Firebase Hosting.
9. Retire Render and Vercel after a stable week.

---

## 4. Files touched (representative)

| Area | New | Modified or removed |
|---|---|---|
| Repo merge | `aml_copilot/` (moved in), `tests/aml_copilot/`, `data/typology_docs/`, `docs/aml/`, `databricks/` | the AML repo is archived; `dbx/webapp.py`, `service/delta.py` and the Salesforce source are removed; `aml_copilot/config.py` (env var names) |
| Data platform | `databricks/jobs/{bronze,silver,gold,profiles,sync,evaluation}.py`, `databricks.yml` targets | — |
| ML detection | `ml/features/` (point-in-time transaction, window and graph features), `ml/train/{lightgbm_m1,m2,m3,multignn}.py`, `ml/score/{batch,serving}.py`, `ml/monitoring/`, `ml/model_cards/`, `databricks/jobs/{train,score,monitor}.yml` | `aml_copilot/detection/risk_score.py` (becomes an ML score client), `aml_copilot/agents/{evidence,typology}.py` |
| Supabase | `supabase/migrations/*.sql`, `src/data/repositories/*.py`, `aml_copilot/service/supabase_store.py`, `aml_copilot/ingestion/supabase_profile.py` | `src/models/database.py` (Postgres only; `run_migrations` removed) |
| Retrieval | `src/rag/backends/{vertex,chroma}.py`, `jobs/index_docs.py` | `src/rag/vector_store.py`, `src/rag/hybrid_retriever.py`, `aml_copilot/retrieval/store.py` |
| AML Copilot | detector rules, `detection/thresholds.py`, typology docs for the 8 IBM patterns | `ids.py`, `agents/investigation.py`, `detection/risk_score.py`, `evaluation/dataset.py` |
| Backend | `src/api/routes/aml_investigations.py`, `src/aml/dispatch.py` | `src/api/main.py`, `src/api/auth.py`, `src/api/routes/{aml,customers,transactions,kpi}.py`, `src/rag/data_retriever.py`, `src/agents/registry.py` |
| Frontend | — | `features/aml/AMLCenter.tsx`, `services/api.ts`, `types/banking.ts`, customer search components |
| GCP | `Dockerfile`, `deployment/gcp/` (Terraform), `.github/workflows/deploy-gcp.yml`, `firebase.json` | `requirements*.txt`, `.env.example` |
| Tests | `tests/test_aml_integration.py`, `tests/fixtures/golden_customers.json`, a label-leak test | every suite that uses `CX-10000x` ids, which switch to the golden fixtures |

Commit and push at the end of each phase.

---

## 5. Production environment: Google Cloud (GCP)

### 5.1 Environments
| Environment | App | Transactions | App database | Vector search | Investigation runs |
|---|---|---|---|---|---|
| Local | `uvicorn` + Vite | Databricks `trustnova_dev` (sampled slice) | Supabase CLI local Postgres | Chroma | `thread` |
| Staging | Cloud Run (`trustnova-staging`) | Databricks `trustnova_staging` | Supabase staging project | Vertex Vector Search (small) | Cloud Tasks |
| **Production** | Cloud Run (`trustnova-prod`) | Databricks `trustnova_prod` (full 430M) | Supabase production project | Vertex Vector Search (autoscaling) | Cloud Tasks |

### 5.2 Services
| Concern | Service | Notes |
|---|---|---|
| Backend and AML pipeline | **Cloud Run** `trustnova-api` | One image with no torch, so it is small. Roughly 1–2 vCPU and 2 GiB, minimum 1 instance, request timeout 15 min. Fixed egress IP through Serverless VPC Access and Cloud NAT, so Supabase can allow-list it. |
| Investigation runs | **Cloud Tasks** queue `aml-investigations` | `max_concurrent_dispatches` starts at 1 and can be raised later. At most 2 retries; duplicate runs are blocked by `investigate(...)`. Calls the OIDC-only internal endpoint. |
| Transactions and analytics | **Databricks on GCP** | Unity Catalog on GCS, a serverless SQL warehouse for API and copilot queries, and job clusters for ingestion, profile generation, sync and evaluation. |
| ML training and serving | **Databricks ML on GCP** | Feature tables plus an online feature store, MLflow tracking, the UC Model Registry (`@champion`, `@challenger`), CPU job clusters for LightGBM, GPU job clusters for Multi-GNN, a serverless **Model Serving** endpoint for on-demand scoring, and Lakehouse Monitoring for drift. |
| Customers and app data | **Supabase** (Postgres, external to GCP) | Pro plan with a compute add-on, point-in-time recovery, daily backups, network allow-list, and a least-privilege role for the API. |
| Vector search | **Vertex AI Vector Search** | Dedicated index endpoint with replica autoscaling. Filter tags on collection and `doc_type`. |
| Embeddings and AML LLMs | **Vertex AI** | Text-embedding model and Claude models. The Vertex region is chosen where the Claude models are offered. |
| Raw data and docs | **Cloud Storage** | `trustnova-prod-raw` (IBM files) and the Unity Catalog storage bucket, both private. |
| Secrets | **Secret Manager** | `JWT_SECRET_KEY`, `GROQ_API_KEY`, the Supabase DB URL, and the Databricks credential (if Google ID-token auth isn't used). |
| Frontend | **Firebase Hosting** | Rewrites `/api/**` to Cloud Run, so frontend and API share one origin and no CORS setup is needed. |
| Images | **Artifact Registry** | Docker images tagged with the git SHA. |
| Observability | **Cloud Logging, Monitoring, Error Reporting** | Alerts on 5xx rate, task failures, investigation latency and Databricks job failures. Budget alerts on Vertex AI, Databricks and Supabase. |

### 5.3 Identity and access
- **Runtime service account `trustnova-api@`:**
  - `aiplatform.user`
  - `secretmanager.secretAccessor` (only its own secrets)
  - `cloudtasks.enqueuer`
  - `run.invoker` on itself, so Cloud Tasks can call the internal endpoint
  - `storage.objectViewer` (docs bucket only)
- **Databricks access.** Prefer letting the Cloud Run service account sign in to Databricks with a Google ID token. If that isn't available, use a Databricks OAuth service principal stored in Secret Manager; its secret expires every 90 days, so add a rotation reminder. Unity Catalog grants:
  - the API principal: `SELECT` on `gold.*` only
  - the evaluation principal: `SELECT` on `silver.aml_labels` and `silver.aml_patterns`
- **CI/CD** signs in to GCP through Workload Identity Federation (already used by AML Copilot), so no key files are created.

### 5.4 Delivery pipeline (GitHub Actions)
1. **On a pull request:** lint, run both test suites against a local Postgres container, run the AML canary evaluation and gitleaks.
2. **On merge to `main`:**
   1. Build and push the image.
   2. Run `supabase db push` (migrations) against staging.
   3. Run `databricks bundle deploy -t staging`.
   4. Deploy Cloud Run staging and Firebase staging.
   5. Run the smoke test.
3. **Production:** after manual approval in GitHub Environments, the same image and steps go to `prod`.
4. **Infrastructure:** Terraform in `deployment/gcp/` (Cloud Run, Tasks, Vector Search, buckets, secrets, IAM, NAT, budgets). The Databricks workspace and Unity Catalog grants are managed with the Databricks Terraform provider in the same folder.

### 5.5 Rough monthly cost drivers (to estimate before cut-over)
- the Vector Search endpoint, which is always on
- the Supabase Pro plan, compute add-on and storage for about 9.5M customers
- the Databricks SQL warehouse and nightly jobs; the one-time backfill of 430M rows is the largest single cost
- Vertex Claude per investigation: AML Copilot's evaluation measured about $0.13 per account
- ML: feature computation over 430M transactions (the one-time backfill, then incremental runs), monthly retraining (Multi-GNN on GPU is the expensive part, so run it only on challenger cycles), batch scoring, and the Model Serving endpoint (scales to zero off-peak)
- Cloud Run with a minimum of 1 instance

---

## 6. Risks and mitigations

| Risk | Mitigation |
|---|---|
| The combined bank is six unconnected groups with a blended laundering rate | Keep the `variant` column, report metrics per variant, and document it in the UI and README. Money-tracing stays within a variant because of the namespaced ids. |
| Ground truth leaking into prompts, profiles or cases | Labels and patterns live in restricted Unity Catalog tables. Profiles and cases come from observable data only. Tests check that no label field reaches the evidence bundle, profiles or the API. |
| Slow lookups across 430M rows | `gold.account_txn_edges` with liquid clustering on account; strict row limits; Supabase `account_summary` for screens; caching. |
| Cross-cloud latency and egress (GCP ↔ Supabase on AWS) | Pick the nearest regions, use connection pooling for the API, keep Supabase queries indexed and narrow, and do bulk loads only from Databricks. |
| Bulk-loading 9.5M customers into Supabase | Batched `COPY` over the direct connection, indexes built after loading, and a resumable loader with checkpoints. |
| Merge regressions (environment variable clash, dependency changes) | Renamed `AML_*` variables; the merge-gate test run (Phase 1.6) before anything else changes. |
| Retrieval quality shifts with the new embedding model | Re-run evaluation; must keep typology precision/recall and ≥ 95% supported sentences, or tune chunking first. |
| Cloud Run throttles background threads after a response | Production runs happen inside the Cloud Tasks request, never in a background thread. |
| Cost of always-on services | Budget alerts, auto-stopping SQL warehouse, a daily investigation quota and `BudgetMeter`. |
| ML label leakage (future data in features, `variant` as a proxy for the laundering rate) | point-in-time feature computation; `variant` and profile fields excluded; temporal split per variant; a test that fails if any banned column reaches the training set |
| Extreme class imbalance hides poor detection | minority-class F1, PR-AUC and recall at the alert budget instead of accuracy; calibration on untouched data; results per variant and per pattern |
| Black-box alerts can't be justified in a SAR or to auditors | LightGBM champion with SHAP reason codes on every alert; the GNN is promoted only with reviewed explanations; model cards and validation reports in the registry |
| Model drift or a degraded model in production | Lakehouse Monitoring, alert-volume guard rails, analyst-outcome tracking, the `@champion` alias for instant rollback, and monthly retraining through the same gate |
| GenAI overriding or inventing detections | agents receive the score read-only; the tier comes only from the model; faithfulness checks and citation stripping stay; a missing ML score makes the run `incomplete` |
| CDLA-Sharing-1.0 obligations | Credit the source in the README and footer. Any derived dataset we publish keeps the same licence. |

---

## 7. Verification (for when it's implemented)
1. **Merge gate.** Both test suites pass in the merged repo with no other changes.
2. **Data platform.**
   - Bronze row counts match each file. Silver total ≈ 430M, and per-variant counts match the Kaggle statistics (5M, 7M, 32M, 31M, 180M, 176M).
   - The API principal gets permission denied on `silver.aml_labels`.
   - A clustered lookup for one account returns within the target (under 2 s on the serverless warehouse).
3. **Supabase.** The customer count equals the number of accounts (or entities). A trigram search returns in under 300 ms. The golden fixtures resolve.
4. **Retrieval.** The indexing job upserts every chunk, and queries honour the `collection` and `doc_type` filters.
5. **ML models**, on the held-out temporal test split:
   - M1 and M2 must beat the rule-only baseline on minority-class F1, PR-AUC and recall at the alert budget, overall and in every variant.
   - M3 is evaluated with per-pattern precision and recall.
   - The challenger is compared side by side. Every registered version has a model card.
   - The leakage test passes.
   - Batch scoring finishes within the scheduled window, and the Model Serving endpoint answers within its latency target.
6. **GenAI agent evaluation** on IBM labels, overall and per variant: typology explanation agrees with the ground truth (or correctly flags disagreement), ≥ 95% of SAR sentences supported, and every reason code cited in the narrative exists in the ML output.
7. **Backend tests.**
   - The RBAC matrix: `kyc` gets 403; `credit_risk_analyst` can read but gets 403 on decisions; `amlanalyst` can do everything.
   - 409 on a duplicate run, rejection on a `result_hash` mismatch, and 403 on the internal endpoint without a valid OIDC token.
   - The label-leak test.
8. **End to end on staging** (this is also the post-deploy smoke test):
   1. Log in as `amlanalyst` and open a fan-out case.
   2. Run an investigation and watch the steps progress to `draft_ready` with citations.
   3. Approve it and confirm `sar_filed` and the audit chain are updated.
   4. Log in as `compliance` and confirm the decision controls are hidden and the API rejects a decision.
9. **Regression.** The existing functional/non-functional (188) and security (35) suites are updated to the golden fixtures and pass against staging, then production.
10. **Load.** The load and stress scripts run against staging, focusing on customer search and Customer 360 over the full 9.5M customers.
