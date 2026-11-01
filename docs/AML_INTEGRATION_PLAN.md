# TrustNova AI + AML Copilot: Merge and Integration Plan

**Status:** Phase 1 done (1 Nov 2026). Phase 0 cloud setup done for GCP and Databricks (1 Nov 2026); Supabase is still to do. Phase 2 next.

**Revision, 1 Nov 2026.** Databricks on GCP needs a paid Google billing account, so transactions and ML now run on the **existing Databricks workspace** (Free Edition on AWS, `us-east-2`, workspace `7474648796792570`). Everything else stays on GCP. The changes are marked *(revised)* below. Moving to Databricks on GCP later only changes the bundle target and the storage path.

## Decisions taken
| Topic | Decision |
|---|---|
| Codebase | **Merge** AML Copilot into the TrustNova AI repo as one product. It runs inside the same backend process. |
| Data | The **entire IBM AML dataset**: all six simulations loaded as **one combined bank**, about 9.5M accounts and 430M transactions. Customers are the dataset's own **account owners** (the `*_accounts.csv` files map every account to an Entity ID). |
| Transactions *(revised)* | The **existing Databricks workspace** (Free Edition, AWS `us-east-2`): Unity Catalog catalogs `trustnova_staging` (the two Small simulations) and `trustnova_prod` (all six). Raw files sit in Unity Catalog volumes inside the workspace, not in Google Cloud Storage. |
| Customers and all app data | **Supabase** (Postgres). Salesforce is retired because it can't hold millions of customers. Cloud SQL and SQLite are retired too. |
| Vector search | **Vertex AI Vector Search**, a dedicated, separately scalable GCP service, with Vertex AI embeddings. |
| AML detection | **Trained machine-learning models** decide what is suspicious. The champion is a **LightGBM** model on transaction and graph features; the challenger is a **graph neural network (Multi-GNN)**. They are trained, registered and served on Databricks (MLflow). GenAI doesn't do detection. *(revised)* Free Edition has no GPU compute, so the Multi-GNN challenger waits until GPU compute is available; LightGBM runs on serverless CPU. |
| GenAI *(revised)* | **Agents only:** the evidence summary, the typology explanation, the SAR narrative, the faithfulness check and chat. The agents explain and document the model's alerts. They never raise or clear an alert themselves. The AML agents default to **Gemini on Vertex AI**: AML Copilot's evaluated setup (97% of sentences supported), and a Google first-party model that doesn't need a paid billing account. Claude on Vertex is a partner model sold through Marketplace, so it waits for a paid account; Claude through the Anthropic API stays an option. |
| Production | **GCP**: Cloud Run, Cloud Tasks, Vertex AI, Secret Manager and Firebase Hosting. This replaces Render and Vercel. Production is `aml-co-pilot` and staging is `trustnova-staging-5619`, both in `us-east4`. |

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
- **Size:** about 39 GB in 18 files: for each simulation, a `*_Trans.csv`, a `*_Patterns.txt` and a `*_accounts.csv`. The Kaggle page lists only the first two.
- **Transaction columns:** `Timestamp, From Bank, Account, To Bank, Account.1, Amount Received, Receiving Currency, Amount Paid, Payment Currency, Payment Format, Is Laundering`.
- **Accounts columns:** `Bank Name, Bank ID, Account Number, Entity ID, Entity Name`. Entity types are Partnership, Corporation, Sole Proprietorship, Country, Individual and Direct. Bank names mostly carry a country (`Germany Bank #4815`).
- **Laundering patterns:** the patterns files label attempts as fan-out, fan-in, cycle, gather-scatter, scatter-gather, stack, bipartite or random.
- **Why it fits:** both sides of every transfer are recorded, which AML Copilot needs to follow money between accounts and detect layering.
- **What it lacks:** KYC, PEP status, demographics, merchants, devices and sentiment.

**Measured on HI-Small before writing any transforms** (5,078,345 rows):
- **Formats:** every timestamp is `yyyy/MM/dd HH:mm`, from 2022/09/01 to 2022/09/18 (later than the 10 days Kaggle states). Every account number is a 9-character uppercase hex string.
- **Bank IDs** are zero-padded in transactions (`010`, `03208`) but not in the accounts file. Once leading zeros are stripped, all 515,088 accounts that appear in transactions match the accounts file exactly.
- **Account numbers** collide across banks 8 times, so account ids must include the bank.
- **Owners:** 518,581 accounts belong to 166,207 entities. 102,689 entities own one account; the rest own between 2 and dozens.
- **Currencies:** 15. 72,170 rows convert currency, at a near-fixed rate per pair (about ±0.3%), so the USD rates are derived from the data. Bitcoin has no direct Bitcoin→USD sample, so it uses the inverse of USD→Bitcoin. Same-currency rows always have paid = received.
- **Patterns:** 370 attempts, 3,209 lines. Every line matches exactly one transaction row, and no line belongs to two attempts. 5,177 transactions are laundering, of which 3,209 (62%) are in a labelled attempt; the rest form an "other" class.
- **Rows:** 9 exact duplicates, which stay as separate transactions, and 591,212 self-transfers (same bank and account, mostly reinvestment and currency conversion).

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
   Supabase Postgres              Databricks (Free Edition,        Vertex AI
   (AWS us-east-2)                AWS us-east-2) — revised         Vector Search index
   customers (owners), KYC,       UC volumes → bronze → silver     (banking_docs + typology_docs)
   users, aml_cases, alerts,      → gold; account_txn_edges        text embeddings
   investigations, audit,         (430M×2); restricted ground      Gemini models (GenAI agents only)
   rag_chunks, account_summary    truth
                                  ML: feature tables → MLflow
                                  → UC Model Registry → batch scoring
                                  + Model Serving endpoint
              ▲                           │
              └──── nightly sync job ─────┘  (account summaries + ML alerts with reason codes)
```

**Who does what:**
- **ML models (Databricks)** decide risk: transaction scores, account scores and the predicted laundering pattern.
- **GenAI agents (Gemini on Vertex AI; Claude when a paid account allows)** investigate and explain those alerts and draft the SAR, but never change a score.
- **Chat (Groq)** answers analysts' questions.

**Local development** uses the same code with:
- the Supabase CLI's local Postgres in Docker
- the `trustnova_staging` catalog (the two Small simulations) in the same Databricks workspace
- Chroma (`VECTOR_BACKEND=chroma`) instead of Vector Search

Postgres runs in every environment, so there are no SQLite/Postgres SQL differences to manage.

---

## 3. Work plan

### Phase 0 — Prerequisites *(revised, mostly done 1 Nov 2026)*
1. **GCP — done.**

   | Item | Production | Staging |
   |---|---|---|
   | Project | `aml-co-pilot` (billing linked to `0142DD-782E9F-1BCB59`) | `trustnova-staging-5619` (new) |
   | APIs | 17 enabled: Compute, IAM, IAM Credentials, STS, Resource Manager, Service Usage, Storage, Vertex AI, Run, Cloud Tasks, Secret Manager, Artifact Registry, Billing Budgets, Firebase, Firebase Hosting, Logging, Monitoring | same |
   | Budget alert | $50/month at 50/90/100% | $50/month at 50/90/100% |
   | Region | `us-east4` | `us-east4` |

   - **Unused buckets:** `gs://aml-co-pilot-ibm-raw` and `gs://aml-co-pilot-uc-managed` (production), `gs://trustnova-staging-5619-ibm-raw` and `gs://trustnova-staging-5619-uc-managed` (staging). They were created for Databricks on GCP. They are private, in `us-east4`, and stay empty or hold only the first uploads until Databricks moves to GCP; delete them if that won't happen.
   - **Model access:** Gemini on Vertex AI needs no extra access. Claude on Vertex AI would need a paid billing account.
2. **Databricks *(revised)* — done.** The existing workspace `7474648796792570` (Free Edition, AWS `us-east-2`), with CLI profile `trustnova` signed in as `prakash.jvj@gmail.com` (OAuth).
   - **Catalogs:** `trustnova_staging` and `trustnova_prod`, each with the schemas `raw`, `bronze`, `silver`, `restricted`, `gold` and `ml`, and the volume `raw.ibm_aml`.
   - **How they were created:** Free Edition creates catalogs only with SQL (`CREATE CATALOG`, using default storage), not through the catalogs API.
   - **SQL warehouse:** the workspace's `Serverless Starter Warehouse` (2X-Small, auto-stops after 10 minutes).
   - **Existing work kept:** AML Copilot's tables and jobs in `workspace.aml_copilot` stay untouched until Phase 5.
3. **Supabase — to do.** Create a Pro project in **AWS `us-east-2`**, next to the Databricks workspace (plus one for staging).
   - Size it for the owner profiles plus indexes.
   - Allow connections only from the Cloud Run egress IP (fixed through Cloud NAT) and the Databricks serverless egress.
4. **Dataset *(revised)* — uploading.** All 18 files from `Downloads\archive` go into the volume `trustnova_prod.raw.ibm_aml`, and the six Small files into `trustnova_staging.raw.ibm_aml`, using `databricks fs cp`. Files already uploaded at the same size are skipped. Raw files never go into git.
   - **Large files are split.** The Databricks Files API takes at most 5 GiB per file, so `HI-Large_Trans.csv` and `LI-Large_Trans.csv` (about 16 GB each) are stored as `<name>.part-NNN.csv`. Every part starts with the header row and is under 4 GB.
   - **Each split file has a manifest** (`<name>.manifest.json`) recording the source size, the total data rows and each part's rows.
   - **Phase 2 depends on this:** Bronze maps `HI-Large_Trans*.csv` to variant `HIL`, and the quality gate checks Bronze row counts against the manifests.

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

**Phase 1 as built (changes from the steps above):**

| Planned | Done instead | Why |
|---|---|---|
| Python 3.12 | **Python 3.11** (`.venv`) | 3.12 isn't installed. 3.11 is already installed, it's what AML Copilot and both CI pipelines use, and it has torch wheels. |
| Retire `service/delta.py` and the Salesforce source now | **Deferred to Phase 5** | Evaluation and the Databricks job runtime still use `delta.py`'s SQL helpers. The Salesforce source is still how investigations get customer profiles. Removing either before its Supabase replacement exists would break working code. |
| Raise the `fastapi<0.137` cap | **Kept** | The only reason to raise it was AML's web app, which is gone, so there's no conflict left. |
| Move torch / sentence-transformers / chromadb to `requirements-local.txt` | **Deferred to Phase 4** | TrustNova's RAG needs them until Vertex AI replaces them. For now there is one `requirements.txt` (runtime), `requirements-dev.txt` (adds test and lint tools), and a light `requirements-aml-ci.txt` (no torch) for AML's fast CI job. |
| `databricks.yml` inside `databricks/` | **Kept at the repo root** | The bundle uses the repo root as its base. `sync.exclude` now leaves out `src/`, `frontend-react/`, `deployment/` and the raw data folders. |
| Adopt AML's `.gitattributes` | **Only its binary rules** | `* text=auto eol=lf` would have changed line endings across all of TrustNova. |

**Also retired:**
- the Databricks App: `dbx/webapp.py`, `dbx/appmain.py`, `dbx/static/`, `dbx/jobs_api.py`, `databricks/app/`
- its scripts: `build_app.py`, `run_local_app.py`, `grant_app_access.py`
- the app's bundle resource and the `warehouse_id` variable
- `tests/test_webapp.py`

**Path changes:**
- typology corpus: `data/typology_docs/`
- local typology index: `data/aml_chroma/`, rebuilt with `python -m aml_copilot.retrieval build`
- evaluation output: `docs/aml/evaluation_results/`
- AML scripts: `scripts/aml/`

**Environment variables:** AML model settings are read only from `AML_LLM_PROVIDER`, `AML_LLM_MODEL` (or the older `ANTHROPIC_MODEL`), `AML_TYPOLOGY_MODEL`, `AML_NARRATIVE_MODEL` and `AML_FAITHFULNESS_MODEL`.

### Phase 2 — Transaction data platform *(revised: existing Databricks workspace)*
These are Databricks Jobs in the merged `databricks/` bundle, on **serverless** compute (Free Edition has no classic clusters).
- **Targets:** bundle target `staging` (catalog `trustnova_staging`, the two Small simulations) and `prod` (catalog `trustnova_prod`, all six), deployed with `databricks bundle deploy -t <target>` using the CLI profile `trustnova`.
- **Order:** staging runs first and must pass every quality check before prod is loaded.
- **Prod volume:** prod is loaded one simulation at a time (Small, then Medium, then Large), so a Free Edition compute quota stops at a clean boundary instead of mid-load.

1. **Bronze** (`<catalog>.bronze`). Auto Loader (`cloudFiles`) reads the volume `<catalog>.raw.ibm_aml`:
   - `bronze.ibm_transactions`: the `*_Trans.csv` files, every column as text, plus `variant` (`HIS`, `HIM`, `HIL`, `LIS`, `LIM` or `LIL`, from the file name), the source file and the ingest time.
   - `bronze.ibm_accounts`: the `*_accounts.csv` files.
   - `bronze.ibm_pattern_lines`: the `*_Patterns.txt` files, one row per line with its line number.
2. **Silver** (`<catalog>.silver`, with ground truth in `<catalog>.restricted`).
   - **Identifiers.** `bank_id` drops leading zeros (`010` → `10`), which is what makes transactions match the accounts file. Account ids become `{variant}:{bank_id}:{account}`, because account numbers collide across banks and across simulations. Entity ids become `{variant}:{entity_id}`.
   - **`silver.transactions`:** one typed row per transaction.
     - `txn_id`: `{variant}-{n}`, where `n` is a row number ordered by every column. It is deterministic; the 9 exact duplicates get consecutive numbers.
     - `ts`: parsed from `yyyy/MM/dd HH:mm`.
     - `from_account`, `to_account`, `from_bank`, `to_bank`, `is_self_transfer`.
     - `amount_paid`, `paid_currency`, `amount_received`, `received_currency`, `payment_format`.
     - `amount_paid_usd`, `amount_received_usd`.
     - `variant`. The label is **not** in this table.
   - **`silver.fx_rates`:** per variant and currency, the USD rate measured from the data's own conversions. It is the median of `received / paid` for X→USD rows, otherwise the inverse of the USD→X median (as for Bitcoin). The table keeps the sample size and spread, so the rates are documented, not invented.
   - **`silver.accounts`:** `account_id`, `entity_id`, `entity_name`, `entity_type` (Partnership, Corporation, Sole Proprietorship, Country, Individual, Direct), `bank_name`, `bank_country` (from names like `Germany Bank #4815`; null otherwise), `variant`.
   - **`restricted.aml_labels`** (`txn_id`, `is_laundering`, `variant`) and **`restricted.aml_patterns`** (`attempt_id`, `pattern_type`, `pattern_detail`, `txn_id`, `variant`). Patterns are parsed from the BEGIN/END blocks and joined to transactions on all fields. The schema grant is limited to the evaluation principal, so the API and copilot principals can't read ground truth.
3. **Gold** (`<catalog>.gold`).
   - **`gold.account_txn_edges`:** one row per (account, transaction, direction), about 860M rows in prod. Columns: `account_id`, `counterparty_id`, `direction`, `ts`, `amount_usd`, `currency`, `payment_format`, `is_self_transfer` and `txn_id`, with liquid clustering on `account_id, ts`. One clustered lookup returns all money in and out of an account. AML link expansion and TrustNova's transaction views both query it.
   - **`gold.account_summary`:** per account, counts and USD totals in and out, distinct counterparties, first and last activity, payment-format and currency mix, and the self-transfer share.
   - **`gold.entity_summary`:** the same per owner. These rows become Supabase customers in Phase 3.
   - ML feature tables follow in Phase 2B.
4. **Quality gate.** A job task that fails the run on any of these:
   - an unparsed timestamp or amount
   - a duplicate `txn_id`
   - a transaction account missing from `silver.accounts`
   - a pattern line that matches no transaction, or more than one
   - an edge count that isn't exactly twice the transaction count
   - per-variant row counts that differ from the source files
   - a currency without a USD rate

   Results go to `gold.quality_runs`.
5. **Moved to Phase 3:** the sync to Supabase, because the Supabase schema is created there.
6. **Costs:** Free Edition compute is free but has a daily quota. The SQL warehouse auto-stops after 10 minutes idle.

**Phase 2 as built (1 Nov 2026):**
- **Code layout.**
  - `trustnova_lake/`: `ibm.py` (file names, id rules, patterns parser, plain Python), `transforms.py` (Spark, DataFrame in → out), `quality.py` (the gate) and `jobs.py` (task entry points).
  - The bundle is `databricks/lakehouse/`, separate from AML Copilot's bundle, with targets `staging` and `prod` and one job `trustnova-lakehouse-<target>` with four tasks: bronze → silver → gold → quality.
- **Changes from the steps above:**

  | Planned | Done instead | Why |
  |---|---|---|
  | Auto Loader | Plain batch reads | The files never change. Each task replaces only the simulations it is given, so re-runs and size-by-size loading are safe. |
  | `{variant}-{row_number}` ids | `{variant}-{24 hex of sha256(all fields)}-{n}` | A row number needs one global sort per simulation (180M rows). With the hash, `n` only numbers exact duplicates. |
  | Timestamps as plain `TIMESTAMP` | `TIMESTAMP_NTZ` | The files carry wall-clock times with no time zone. |
  | Casts that fail on a bad value | `try_cast` / `try_to_timestamp` | A bad value becomes a null that the quality gate counts, instead of crashing the job. |
  | Pattern matches only in `aml_patterns` | Also `restricted.pattern_line_matches` | The gate needs the per-line match counts. |
- **Grants:** restricted-schema grants wait until the API and evaluation service principals exist (Phase 6). Until then only the owner can read the ground truth.
- **Tests:** 44 local Spark tests (`tests/lake`, with Java 17 and pyspark) run on a small bank in the exact IBM formats; the whole repo has 912 tests passing.
- **Staging run:** HI-Small + LI-Small loaded in about 5 minutes, and all 26 quality checks passed.

  | | HIS | LIS |
  |---|---|---|
  | Transactions | 5,078,345 | 6,924,049 |
  | Laundering | 5,177 | 3,565 |
  | Pattern lines matched | 3,209 / 3,209 | 1,023 / 1,023 |
  | Edges | 10,156,690 | 13,848,098 |
  | Owners | 166,207 | 224,931 |
  | Accounts | 518,581 | 712,688 |

  - Every currency's USD rate was measured from at least 44 conversions, with spreads under 1%.
  - A single-account lookup on the edges table takes about 3 seconds end to end.
- **Note for Phase 3:** a few "Country" and "Direct" entities own thousands of accounts (up to 8,899). They behave like system or central-bank accounts, not ordinary customers, so the customer load should mark or exclude them.

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
- **Challenger: Multi-GNN.** This is IBM's open-source PNA-based graph neural network for directed multigraphs, with edge updates, reverse message passing, ego IDs and port numbering. It is trained for M1 on GPU compute. *(revised)* Free Edition has no GPUs, so the challenger is built once GPU compute is available: a paid Databricks workspace, or a GPU job elsewhere reading the same gold tables. Until then the champion is compared with the rule baseline only.
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
- **Online.** A **Databricks Model Serving** endpoint (serverless, scales to zero off-peak) serves M2 and M3 so the copilot can re-score an account on demand when an analyst opens an investigation. Features are looked up from the online feature table. *(revised)* If Free Edition doesn't allow a custom-model endpoint, the copilot reads the latest batch score from `ml.ml_scores` instead and states the score's age in the evidence.
- **Every score records its `model_name@version`**, so any case can be traced to the exact model that raised it.

**Phase 2B as built so far (1 Nov 2026):**
- **Code.**
  - `trustnova_ml/`: `features.py` (82 point-in-time features), `baseline.py` (rules), `metrics.py` (from binned counts), `train.py` (LightGBM M1 and M3, calibration, reasons, gate) and `jobs.py`.
  - Three bundle jobs: `ml_train` (features → train), `ml_promote` (the manual approval) and `ml_score`.
  - 17 more local tests, so 61 in `tests/lake`.
- **Changes from the steps above:**

  | Planned | Done instead | Why |
  |---|---|---|
  | M2 trained as its own model | Version 1 is the highest calibrated M1 score of the account's transactions that day | A trained M2 is added only if it beats that. |
  | SHAP reason codes | LightGBM's built-in per-feature contributions | Same tree-path attributions as tree SHAP, without the extra library. |
  | 2-hop counterparty-risk feature | Deferred | It needs scores from an earlier run. |
  | Multi-GNN challenger | Deferred | It needs GPUs, which Free Edition doesn't have. |
  | Online feature store and Model Serving | Not built yet | Scoring is batch-only for now. |
- **First staging run (HI-Small + LI-Small, 7 minutes).**
  - Training used 210,144 rows (4,110 laundering, plus normal rows sampled at about 50 per laundering transaction).
  - The test split is the last 20% of each simulation: 2,400,934 rows, 2,723 laundering.

  | Test split | M1 PR-AUC | Rule baseline PR-AUC | M1 recall, top 0.5% | Baseline recall, top 0.5% |
  |---|---|---|---|---|
  | Both | 0.447 | 0.0016 | 67.3% | 0.6% |
  | HI-Small | 0.595 | 0.0029 | 74.6% | 0.6% |
  | LI-Small | 0.228 | 0.0006 | 50.7% | 0.6% |

  - **Alert threshold** (chosen on validation): precision 68%, recall 35%, 1,418 rows flagged.
  - **Recall by pattern:** 50–71% for the eight labelled patterns, but **1.7% for "OTHER"** (laundering outside any labelled attempt, 38% of test positives). That's the main gap to work on.
  - **M3:** macro-F1 0.335, against 0.061 for always guessing the most common pattern.
  - **Gate:** passed. `trustnova_staging.ml.m1_transaction_risk` v1 is `@candidate`, and promotion to `@champion` waits for your approval.
  - **The baseline is weak:** the copied rule thresholds barely fire on this data. A stronger, tuned rule set should be added before production, so the gate means more.

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
2. **Customers from accounts.** The download includes the account-to-owner mapping (`*_accounts.csv`), so **customers are the IBM entities** (`gold.entity_summary`) and `customer_accounts` maps their accounts; HI-Small alone has 166K owners for 519K accounts. `customer_type` comes from the entity type (Corporation, Partnership, Sole Proprietorship, Individual and so on), and the country from the bank. Accounts are never grouped any other way, because that would invent links between accounts and mislead link analysis.
3. **Synthetic profiles at scale.**
   - Generate the missing fields (contact details, KYC dates, PEP flags and the like) in Databricks with a pandas UDF and Faker, seeded by a hash of the entity id, so every profile can be reproduced with no stored state.
   - `customer_type` and country come from the dataset itself, as above.
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
   - *(revised)* The pipeline uses Gemini on Vertex AI (`AML_LLM_PROVIDER=gemini`, `GCP_AUTH=adc`, project `aml-co-pilot`): a Flash model for summaries and a Pro model for typology, narrative and faithfulness, as AML Copilot's bundle already configures.
   - Claude on Vertex (`claude-haiku-4-5` and `claude-sonnet-5`) is a one-setting switch once a paid billing account allows partner models.
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
| Local | `uvicorn` + Vite | Databricks `trustnova_staging` (Small simulations) | Supabase CLI local Postgres | Chroma | `thread` |
| Staging | Cloud Run in `trustnova-staging-5619` | Databricks `trustnova_staging` | Supabase staging project | Vertex Vector Search (small) | Cloud Tasks |
| **Production** | Cloud Run in `aml-co-pilot` | Databricks `trustnova_prod` (all six simulations) | Supabase production project | Vertex Vector Search (autoscaling) | Cloud Tasks |

*(revised)* Both Databricks catalogs live in the one existing workspace (`7474648796792570`, Free Edition, AWS `us-east-2`), so staging and production are separated by catalog rather than by workspace.

### 5.2 Services
| Concern | Service | Notes |
|---|---|---|
| Backend and AML pipeline | **Cloud Run** `trustnova-api` | One image with no torch, so it is small. Roughly 1–2 vCPU and 2 GiB, minimum 1 instance, request timeout 15 min. Fixed egress IP through Serverless VPC Access and Cloud NAT, so Supabase can allow-list it. |
| Investigation runs | **Cloud Tasks** queue `aml-investigations` | `max_concurrent_dispatches` starts at 1 and can be raised later. At most 2 retries; duplicate runs are blocked by `investigate(...)`. Calls the OIDC-only internal endpoint. |
| Transactions and analytics *(revised)* | **Databricks**, the existing Free Edition workspace on AWS `us-east-2` | Unity Catalog with default storage. The raw files sit in volumes. The 2X-Small serverless SQL warehouse serves API and copilot queries, and serverless jobs do ingestion, profiles, sync and evaluation. Free Edition has a daily compute quota. |
| ML training and serving *(revised)* | **Databricks ML** (same workspace) | MLflow tracking, the UC Model Registry (`@champion`, `@challenger`), serverless CPU jobs for LightGBM, batch scoring, Model Serving if Free Edition allows custom models (otherwise the batch scores), and Lakehouse Monitoring. There is no GPU, so the Multi-GNN challenger waits for GPU compute. |
| Customers and app data | **Supabase** (Postgres, external to GCP) | Pro plan with a compute add-on, point-in-time recovery, daily backups, network allow-list, and a least-privilege role for the API. |
| Vector search | **Vertex AI Vector Search** | Dedicated index endpoint with replica autoscaling. Filter tags on collection and `doc_type`. |
| Embeddings and AML LLMs *(revised)* | **Vertex AI** | Text-embedding model and Gemini models, both Google first-party. Claude models later, with a paid account. |
| Raw data *(revised)* | **Databricks volumes** | `trustnova_prod.raw.ibm_aml` and `trustnova_staging.raw.ibm_aml`. The GCS buckets from Phase 0 aren't used while Databricks is on AWS. |
| Secrets | **Secret Manager** | `JWT_SECRET_KEY`, `GROQ_API_KEY`, the Supabase DB URL and the Databricks service principal's OAuth secret. |
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
- **Databricks access** *(revised)*. The workspace is on AWS, so Cloud Run can't sign in with a Google identity. It uses a Databricks OAuth service principal (machine-to-machine) whose secret lives in Secret Manager. Secrets expire after at most 90 days, so add a rotation reminder. Unity Catalog grants, per catalog:
  - the API principal: `USE` and `SELECT` on `gold` only
  - the evaluation principal: also `SELECT` on `restricted`
  - CLI deploys use your own OAuth sign-in (profile `trustnova`)
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
4. **Infrastructure:** Terraform in `deployment/gcp/` (Cloud Run, Tasks, Vector Search, buckets, secrets, IAM, NAT, budgets). *(revised)* The Databricks catalogs, schemas and volumes are created by a checked-in SQL setup script, because Free Edition creates catalogs only through SQL. Grants come from the same script.

### 5.5 Rough monthly cost drivers (to estimate before cut-over)
- **The Vector Search endpoint, which is always on.** *(revised)* A deployed index keeps at least one node running at all times, which on its own can approach or pass the $50/month budget. Price it before Phase 4, and if it doesn't fit, choose between a higher budget and a cheaper store (for example `pgvector` in Supabase).
- the Supabase Pro plan, compute add-on and storage for the owner profiles
- *(revised)* Databricks Free Edition costs nothing but has a daily compute quota. The one-time load of 430M rows may need to run over several days, one simulation at a time.
- *(revised)* Vertex Gemini per investigation: AML Copilot measured about $0.16 per account with Gemini ($3.36 for 21 accounts)
- ML: feature computation over 430M transactions (the one-time backfill, then incremental runs), monthly retraining, batch scoring, and Model Serving if available
- Cloud Run with a minimum of 1 instance

---

## 6. Risks and mitigations

| Risk | Mitigation |
|---|---|
| The combined bank is six unconnected groups with a blended laundering rate | Keep the `variant` column, report metrics per variant, and document it in the UI and README. Money-tracing stays within a variant because of the namespaced ids. |
| Ground truth leaking into prompts, profiles or cases | Labels and patterns live in restricted Unity Catalog tables. Profiles and cases come from observable data only. Tests check that no label field reaches the evidence bundle, profiles or the API. |
| Slow lookups across 430M rows | `gold.account_txn_edges` with liquid clustering on account; strict row limits; Supabase `account_summary` for screens; caching. |
| Cross-cloud latency and egress (Cloud Run on GCP `us-east4` ↔ Databricks and Supabase on AWS `us-east-2`) *(revised)* | Supabase goes in the same AWS region as Databricks, so bulk loads stay inside AWS. The API uses connection pooling, narrow indexed queries and row limits. Databricks results for screens come from Supabase `account_summary`, not live warehouse queries. |
| Free Edition limits (daily compute quota, one 2X-Small warehouse, no GPUs, no classic clusters) *(revised)* | Prove everything on `trustnova_staging` first; load prod one simulation at a time and resume where a quota stops it; keep the Multi-GNN challenger and Model Serving optional; moving to a paid workspace (on GCP or AWS) only changes the bundle target, the storage path and the grants script. |
| The GCP billing account isn't a paid account *(revised)* | Use Google first-party services only (Gemini, embeddings, Cloud Run and the rest). Partner models (Claude on Vertex) and Databricks on GCP wait for a paid account. |
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
